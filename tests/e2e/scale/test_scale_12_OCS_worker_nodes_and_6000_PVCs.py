import logging
import pytest

from ocs_ci.ocs import constants, scale_lib, cluster
from ocs_ci.utility import utils
from ocs_ci.utility.utils import ocsci_log_path
from ocs_ci.ocs.scale_lib import FioPodScale
from ocs_ci.helpers import disruption_helpers
from ocs_ci.ocs.node import get_worker_nodes
from ocs_ci.framework.testlib import scale, E2ETest, ignore_leftovers
from ocs_ci.framework.pytest_customization.marks import (
    skipif_aws_i3,
    skipif_bm,
    skipif_external_mode,
)

logger = logging.getLogger(__name__)

# Scale data file
log_path = ocsci_log_path()
SCALE_DATA_FILE = f"{log_path}/scale_data_file.yaml"


@ignore_leftovers
@scale
@skipif_aws_i3
@skipif_bm
@skipif_external_mode
class TestAddNode(E2ETest):
    """
    Automates adding worker nodes to the cluster while IOs
    """

    def test_scale_node_and_capacity(self):
        """
        Test for scaling 12 OCS worker nodes to the cluster
        Scale 12*3 = 36 OSDs
        """

        expected_worker_count = 12
        # Check existing OSD count and add OSDs if required
        existing_osd_count = cluster.count_cluster_osd()
        if existing_osd_count == 3 or existing_osd_count == 6:
            scale_lib.scale_osd_capacity(expected_osd_count=9)

        # Check existing OCS worker node count and add nodes if required
        existing_ocs_worker_list = get_worker_nodes()
        if len(existing_ocs_worker_list) < expected_worker_count:
            scale_worker_count = expected_worker_count - len(existing_ocs_worker_list)
            scale_lib.scale_ocs_node(node_count=scale_worker_count)
            scale_osd_count = expected_worker_count * 3
            scale_lib.scale_osd_capacity(expected_osd_count=scale_osd_count)

    def test_scale_pvcs_pods(self):
        """
        Scale 6000 PVCs and PODs in cluster with 12 worker nodes
        """

        scale_count = 6000
        pvcs_per_pod = 20
        # Scale
        fioscale = FioPodScale(
            kind=constants.DEPLOYMENTCONFIG, node_selector=constants.SCALE_NODE_SELECTOR
        )
        kube_pod_obj_list, kube_pvc_obj_list = fioscale.create_scale_pods(
            scale_count=scale_count, pvc_per_pod_count=pvcs_per_pod
        )

        namespace = fioscale.namespace
        scale_round_up_count = scale_count + 80

        # Get PVCs and PODs count and list
        pod_running_list, pvc_bound_list = ([], [])
        for pod_objs in kube_pod_obj_list:
            pod_running_list.extend(
                scale_lib.check_all_pod_reached_running_state_in_kube_job(
                    kube_job_obj=pod_objs,
                    namespace=namespace,
                    no_of_pod=int(scale_round_up_count / 160),
                )
            )
        for pvc_objs in kube_pvc_obj_list:
            pvc_bound_list.extend(
                scale_lib.check_all_pvc_reached_bound_state_in_kube_job(
                    kube_job_obj=pvc_objs,
                    namespace=namespace,
                    no_of_pvc=int(scale_round_up_count / 16),
                )
            )

        logging.info(
            f"Running PODs count {len(pod_running_list)} & "
            f"Bound PVCs count {len(pvc_bound_list)} "
            f"in namespace {fioscale.namespace}"
        )

        # Write namespace, PVC and POD data in a SCALE_DATA_FILE which
        # will be used during post_upgrade validation tests
        with open(SCALE_DATA_FILE, "a+") as w_obj:
            w_obj.write(str("# Scale Data File\n"))
            w_obj.write(str(f"NAMESPACE: {namespace}\n"))
            w_obj.write(str(f"POD_SCALE_LIST: {pod_running_list}\n"))
            w_obj.write(str(f"PVC_SCALE_LIST: {pvc_bound_list}\n"))

        # Check ceph health status
        utils.ceph_health_check(tries=30)

    @pytest.mark.parametrize(
        argnames="resource_to_delete",
        argvalues=[
            pytest.param(*["mgr"], marks=[pytest.mark.polarion_id("OCS-766")]),
            pytest.param(*["mon"], marks=[pytest.mark.polarion_id("OCS-764")]),
            pytest.param(*["osd"], marks=[pytest.mark.polarion_id("OCS-765")]),
            pytest.param(*["mds"], marks=[pytest.mark.polarion_id("OCS-613")]),
            pytest.param(
                *["cephfsplugin"], marks=[pytest.mark.polarion_id("OCS-1891")]
            ),
            pytest.param(*["rbdplugin"], marks=[pytest.mark.polarion_id("OCS-1891")]),
            pytest.param(
                *["cephfsplugin_provisioner"],
                marks=[pytest.mark.polarion_id("OCS-1891")]
            ),
            pytest.param(
                *["rbdplugin_provisioner"], marks=[pytest.mark.polarion_id("OCS-1891")]
            ),
            pytest.param(*["operator"], marks=[pytest.mark.polarion_id("OCS-1890")]),
        ],
    )
    def test_respin_ceph_pods(self, resource_to_delete):
        """
        Test re-spin of Ceph daemond pods, Operator and CSI Pods
        in Scaled cluster
        """

        disruption = disruption_helpers.Disruptions()
        disruption.set_resource(resource=resource_to_delete)
        no_of_resource = disruption.resource_count
        for i in range(0, no_of_resource):
            disruption.delete_resource(resource_id=i)

        utils.ceph_health_check()

        # Get info from SCALE_DATA_FILE for validation
        file_data = templating.load_yaml(SCALE_DATA_FILE)
        namespace = file_data.get("NAMESPACE")
        pod_scale_list = file_data.get("POD_SCALE_LIST")
        pvc_scale_list = file_data.get("PVC_SCALE_LIST")

        # Get all PVCs from namespace
        all_pvc_dict = get_all_pvcs(namespace=namespace)
        pvc_bound_list, pvc_not_bound_list = ([], [])
        for i in range(len(pvc_scale_list)):
            pvc_data = all_pvc_dict["items"][i]
            if not pvc_data["status"]["phase"] == constants.STATUS_BOUND:
                pvc_not_bound_list.append(pvc_data["metadata"]["name"])
            else:
                pvc_bound_list.append(pvc_data["metadata"]["name"])

        # Get all PODs from namespace
        ocp_pod_obj = OCP(kind=constants.DEPLOYMENTCONFIG, namespace=namespace)
        all_pods_dict = ocp_pod_obj.get()
        pod_running_list, pod_not_running_list = ([], [])
        for i in range(len(pod_scale_list)):
            pod_data = all_pods_dict["items"][i]
            if not pod_data["status"]["availableReplicas"]:
                pod_not_running_list.append(pod_data["metadata"]["name"])
            else:
                pod_running_list.append(pod_data["metadata"]["name"])

        # Check status of PVCs PODs scaled in pre-upgrade
        if not len(pvc_bound_list) == len(pvc_scale_list):
            raise UnexpectedBehaviour(
                f"PVC Bound count mismatch {len(pvc_not_bound_list)} PVCs not in Bound state "
                f"PVCs not in Bound state {pvc_not_bound_list}"
            )
        else:
            logging.info(f"All the expected {len(pvc_bound_list)} PVCs are in Bound state")

        if not len(pod_running_list) == len(pod_scale_list):
            raise UnexpectedBehaviour(
                f"POD Running count mismatch {len(pod_not_running_list)} PODs not in Running state "
                f"PODs not in Running state {pod_not_running_list}"
            )
        else:
            logging.info(
                f"All the expected {len(pod_running_list)} PODs are in Running state"
            )

        # Check ceph health status
        utils.ceph_health_check()

    @pytest.mark.parametrize(
        argnames=["node_type"],
        argvalues=[
            pytest.param(*["worker"], marks=pytest.mark.polarion_id("OCS-763")),
            pytest.param(*["master"], marks=pytest.mark.polarion_id("OCS-754")),
        ],
    )
    def test_reboot_nodes(self, node_type):
        """
        Test reboot of master and OCS worker nodes in scaled cluster
        """

        # TODO
        pass

    @pytest.mark.polarion_id("OCS-760")
    def test_shutdown_nodes(self):
        """
        Test shutdown of master and OCS worker nodes in scaled cluster
        """
        # TODO
        pass

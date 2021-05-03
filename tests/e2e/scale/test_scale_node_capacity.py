import logging
import pytest

from ocs_ci.ocs import constants, scale_lib, cluster
from ocs_ci.utility import utils
from ocs_ci.ocs.scale_lib import FioPodScale
from ocs_ci.helpers import disruption_helpers
from ocs_ci.ocs.node import get_worker_nodes
from ocs_ci.framework.testlib import scale, E2ETest, ignore_leftovers
from ocs_ci.framework.pytest_customization.marks import (
    skipif_aws_i3, skipif_bm, skipif_external_mode
)

logger = logging.getLogger(__name__)


@ignore_leftovers
@scale
@skipif_aws_i3
@skipif_bm
@skipif_external_mode
class TestAddNode(E2ETest):
    """
    Automates adding worker nodes to the cluster while IOs
    """
    def test_scale_node_capacity(self):
        """
        Test for scaling 12 OCS worker nodes to the cluster
        Scale 12*3 = 36 OSDs
        """

        expected_worker_count = 12
        # Check existing OSD count and add OSDs if required
        existing_osd_count = cluster.count_cluster_osd()
        if existing_osd_count == 3:
            scale_lib.scale_osd_capacity(storagecluster_replica_count=3)

        # Check existing OCS worker node count and add nodes if required
        existing_ocs_worker_list = get_worker_nodes()
        if len(existing_ocs_worker_list) < expected_worker_count:
            scale_worker_count = expected_worker_count - len(existing_ocs_worker_list)
            scale_lib.scale_ocs_node(node_count=scale_worker_count)
            scale_lib.scale_osd_capacity()

    def test_scale_pvcs_pods(self):
        """
        Scale 6000 PVCs and PODs in cluster with 12 worker nodes
        """

        # Scale
        fioscale = FioPodScale(
            kind=constants.DEPLOYMENTCONFIG, node_selector=constants.SCALE_NODE_SELECTOR
        )
        fioscale.create_scale_pods(
            scale_count=6000, pvc_per_pod_count=20
        )

    @pytest.mark.parametrize(
        argnames="resource_to_delete",
        argvalues=[
            pytest.param(*["mgr"], marks=[pytest.mark.polarion_id("OCS-766")]),
            pytest.param(*["mon"], marks=[pytest.mark.polarion_id("OCS-764")]),
            pytest.param(*["osd"], marks=[pytest.mark.polarion_id("OCS-765")]),
            pytest.param(*["mds"], marks=[pytest.mark.polarion_id("OCS-613")]),
            pytest.param(*["cephfsplugin"], marks=[pytest.mark.polarion_id("OCS-1891")]),
            pytest.param(*["rbdplugin"], marks=[pytest.mark.polarion_id("OCS-1891")]),
            pytest.param(
                *["cephfsplugin_provisioner"],
                marks=[pytest.mark.polarion_id("OCS-1891")]
            ),
            pytest.param(
                *["rbdplugin_provisioner"],
                marks=[pytest.mark.polarion_id("OCS-1891")]
            ),
            pytest.param(
                *["operator"],
                marks=[pytest.mark.polarion_id("OCS-1890")]
            ),
        ]
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

    @pytest.mark.parametrize(
        argnames=["node_type"],
        argvalues=[
            pytest.param(*["worker"], marks=pytest.mark.polarion_id("OCS-763")),
            pytest.param(*["master"], marks=pytest.mark.polarion_id("OCS-754")),
        ],
    )
    def test_reboot_nodes(self):
        """
        Test reboot of master and OCS worker nodes in scaled cluster
        """

        # TODO
        pass

    @pytest.mark.parametrize(
        pytest.mark.polarion_id("OCS-760")
    )
    def test_shutdown_nodes(self):
        """
        Test shutdown of master and OCS worker nodes in scaled cluster
        """
        # TODO
        pass

import logging

# import pytest

from time import sleep

from ocs_ci.framework import config
from ocs_ci.framework.testlib import rdr_test
from ocs_ci.helpers import dr_helpers
from ocs_ci.helpers.dr_helpers import get_current_primary_cluster_name

# from ocs_ci.ocs.node import wait_for_nodes_status, get_node_objs
from ocs_ci.utility import version

logger = logging.getLogger(__name__)


@rdr_test
class KRBDBlocklistAlert:
    """
    Check alert when kernel ip of a node gets blocklisted
    """

    def krbd_blocklist_alert(self, setup_ui_clas, rdr_workload):
        """
        Test to check if alert is triggered on the OCP console when kernel ip of a node gets blocklisted
        Mostly, the alert is expected to be triggered on the primary managed cluster where workloads are running
        due to ip blocklist.

        """

        self.ocs_version_semantic = version.get_semantic_ocs_version_from_config()
        # --> add skip
        if self.ocs_version_semantic >= version.VERSION_4_13:
            dr_helpers.set_current_primary_cluster_context(
                rdr_workload.workload_namespace
            )
            _ = config.cur_index
            scheduling_interval = dr_helpers.get_scheduling_interval(
                rdr_workload.workload_namespace
            )
            wait_time = 2 * scheduling_interval  # Time in minutes
            logger.info(f"Waiting for {wait_time} minutes to run IOs")
            sleep(wait_time * 60)

            _ = get_current_primary_cluster_name

        else:
            logger.error("ODF version 4.13 and above is supported for this feature")
            raise NotImplementedError

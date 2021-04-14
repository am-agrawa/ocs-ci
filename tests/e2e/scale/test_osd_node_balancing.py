"""
Test osd node balancing by adding nodes and osds and checking their distribution
"""
import logging
from ocs_ci.framework.testlib import scale, E2ETest, ignore_leftovers
from ocs_ci.ocs import constants, machine, ocp
from ocs_ci.ocs.node import add_new_node_and_label_it, get_osd_running_nodes, get_nodes
from ocs_ci.ocs.resources import storage_cluster
from ocs_ci.utility.utils import (
    ceph_health_check,
    TimeoutSampler,
    ocsci_log_path,
    get_az_count,
)

REPORT = "Node_and_Osd_distribution_report.txt"
FINAL_REPORT = "Final Report"
MAX_NODE_COUNT = 9
MAX_OSDS_PER_NODE = 3
START_NODE_NUM = 3
REPLICA_COUNT = 3
OSD_LIMIT_AT_START = MAX_OSDS_PER_NODE * START_NODE_NUM
NUM_NODE_ADDS = MAX_NODE_COUNT // REPLICA_COUNT


def add_some_worker_nodes():
    """
    Add three worker nodes to the storage cluster.  Update the report file.
    """
    wnodecnt = len(get_nodes(constants.WORKER_MACHINE))
    if wnodecnt == MAX_NODE_COUNT:
        return
    osd_running_nodes = get_osd_running_nodes()
    logging.info(f"OSDs are running on nodes {osd_running_nodes}")
    # Get the machine name using the node name
    machine_names = [
        machine.get_machine_from_node_name(osd_node) for osd_node in osd_running_nodes
    ]
    logging.info(f"{osd_running_nodes} associated " f"machine are {machine_names}")
    # Get the machineset name using machine name
    machineset_names = [
        machine.get_machineset_from_machine_name(machine_name)
        for machine_name in machine_names
    ]
    logging.info(f"{osd_running_nodes} associated machineset ")
    node_obj = ocp.OCP(kind="node")
    # This next section makes a new node on which OSD pods can run
    for mnames in range(0, NUM_NODE_ADDS):
        # This next section makes a new node on which OSD pods can run
        new_node = add_new_node_and_label_it(
            machineset_names[mnames], mark_for_ocs_label=False
        )
        node_obj.add_label(
            resource_name=new_node[0], label=constants.OPERATOR_NODE_LABEL
        )
    collect_stats("Three nodes have been added")


def increase_osd_capacity():
    """
    Add three osds to the cluster.  Update the report file.
    """
    # This next section increases the number of OSDs on each node by one.
    osd_running_nodes = get_osd_running_nodes()
    osd_size = storage_cluster.get_osd_size()
    logging.info(f"Adding one new set of OSDs. osd size = {osd_size}")
    storagedeviceset_count = storage_cluster.add_capacity(osd_size)
    if type(storagedeviceset_count) == bool:
        logging.info("storeagedeviceset is boolean")
    else:
        logging.info(f"storeagedeviceset is {storagedeviceset_count}")
        logging.info("Adding one new set of OSDs was issued without problems")
        new_osd_count = len(osd_running_nodes) + 3
        pod_obj = ocp.OCP(kind=constants.POD, namespace="openshift-storage")
        for new_osd_list in TimeoutSampler(
            120, 30, lambda: pod_obj.get(selector=constants.OSD_APP_LABEL)["items"]
        ):
            if len(new_osd_list) == new_osd_count:
                break
    ceph_health_check(tries=30, delay=60)
    collect_stats("OSD capacity has been increased")


def collect_stats(action_text):
    """
    Write the current configuration information into the REPORT file.
    This information includes the osd, nodes and which osds are on which
    nodes.  The minimum and maximum numbers of osds per node are also
    computed and saved.  If this is the final call to collect_stats
    (action_text parameter is FINAL_REPORT), then the data collected
    in the REPORT file is also displayed in the log.

    Args:
        action_text -- Title of last action taken
                (usually adding nodes or adding osds)
    """
    pod_obj = ocp.OCP(
        kind=constants.POD, namespace=constants.OPENSHIFT_STORAGE_NAMESPACE
    )
    osd_list = pod_obj.get(selector=constants.OSD_APP_LABEL)["items"]
    node_stats = {}
    for osd_ent in osd_list:
        try:
            osd_node = osd_ent["spec"]["nodeName"]
        except KeyError:
            continue
        if osd_node in node_stats:
            node_stats[osd_node].append(osd_ent)
        else:
            node_stats[osd_node] = [osd_ent]
    osds_per_node = []
    for entry in node_stats:
        osds_per_node.append(len(node_stats[entry]))
    wnodes = get_nodes(constants.WORKER_MACHINE)
    for wnode in wnodes:
        logging.info(wnode.name)
        if wnode.name not in node_stats:
            osds_per_node.append(0)
    maxov = max(osds_per_node)
    minov = min(osds_per_node)
    this_skew = maxov - minov
    logging.info(f"Skew found is {this_skew}")
    logpath = ocsci_log_path()
    outfile = f"{logpath}/{REPORT}"
    with open(outfile, "a+") as fd:
        fd.write(f"\nAction: {action_text}\n\n")
        fd.write(f"Current OSDS: {len(osd_list)}\n")
        for entry in osd_list:
            fd.write(f"\t\t{entry['metadata']['name']}\n")
        fd.write(f"\nCurrent Nodes: {len(wnodes)}\n")
        for entry in wnodes:
            fd.write(f"\t\t{entry.name}\n")
        fd.write("\nOSD distribution:\n")
        for entry in osd_list:
            fd.write(f"\t\t{entry['metadata']['name']}")
            try:
                fd.write(f" is on {entry['spec']['nodeName']}\n")
            except KeyError:
                fd.write(" is on an unknown node\n")
        fd.write(f"\nMaximum number of OSDs on a node: {maxov}\n")
        fd.write(f"Minimum number of OSDs on a node: {minov}\n")
        fd.write(f"Skew (Difference in OSD counts): {this_skew}\n")
        if this_skew > 1:
            fd.write("\n*** ERROR *** OSDs are not balanced between nodes\n")
        else:
            fd.write("\n*** OSDs are evenly distributed ***\n")
        fd.write("\n-------------------------------------------------------------\n")
    if action_text == FINAL_REPORT:
        with open(outfile, "r") as fd:
            logged_info = fd.read()
            for inline in logged_info.split("\n"):
                logging.info(inline)
        logging.info(f"Summary of test results output in {outfile}")


@ignore_leftovers
@scale
class Test_Prototype(E2ETest):
    """
    There is no cleanup code in this test because the final
    state is much different from the original configuration
    (several nodes and osds have been added)
    """

    def test_osd_balance(self):
        """
        Current pattern is:
            add 6 osds (9 total, 3 nodes)
            add 3 nodes
            add 9 osds (18 total, 6 nodes)
            add 3 nodes
            add 9 osds (27 total, 9 nodes)
        """
        if get_az_count() == 1:
            logging.info("WARNING -- not enough availability zones")
        ltext = ["first", "second", "third"]
        collect_stats("Initial Setup")
        pod_obj = ocp.OCP(
            kind=constants.POD, namespace=constants.OPENSHIFT_STORAGE_NAMESPACE
        )
        osd_list = pod_obj.get(selector=constants.OSD_APP_LABEL)["items"]
        cnt = len(osd_list)
        if cnt < OSD_LIMIT_AT_START:
            clim = cnt // REPLICA_COUNT
            for osd_cnt in range(clim, REPLICA_COUNT):
                cntval = ltext[osd_cnt]
                logging.info(f"Adding {cntval} set of osds to original node")
                increase_osd_capacity()
        for _ in range(0, NUM_NODE_ADDS - 1):
            add_some_worker_nodes()
            for osd_cnt in range(0, MAX_OSDS_PER_NODE):
                cntval = ltext[osd_cnt]
                logging.info(f"Adding {cntval} set of osds to new node")
                increase_osd_capacity()
        collect_stats(FINAL_REPORT)

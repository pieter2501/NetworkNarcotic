import argparse             # Required for argument passing
import yaml                 # Required for reading input files
import networkx as nx       # Required for drawing topologies
import json                 # Required for writing output files
import copy                 # Required for creating shallow copies in for loops
from schema import Schema, SchemaError, Optional, And, Or, Regex # Required for reading input files
from uuid import uuid4      # Required for generating GNS3-compatible randoms
from collections import deque # Required for shifting connections
import psutil               # Required for finding which interface on the system has internet access
import subprocess           # Required for finding which interface on the system has internet access

"""
###################################################################################################################
Setting up argument parsing.

This section allows the user to specify arguments when calling the script from the CLI, such as --help.
###################################################################################################################
"""
parser = argparse.ArgumentParser(
    prog="nn.py",
    description="Converts a NetworkNarcotic input file into a .gns3 project file.",
    epilog="https://github.com/pieter2501/NetworkNarcotic")

parser.add_argument("-n", "--name", default="My NetworkNarcotic generated network", help="the name of this project")
parser.add_argument("-i", "--input", required=True, help="the input file")
parser.add_argument("-o", "--output", required=True, help="the output file")

args = parser.parse_args()

"""
###################################################################################################################
Defining global variables.

This section specifies variables that display repeated use throughout the script.
###################################################################################################################
"""
str_IMAGE = "c2600-adventerprisek9-mz.124-15.T14.image"
str_IMAGE_MD5 = "483e3a579a5144ec23f2f160d4b0c0e2"
str_IMAGE_PLATFORM = "c2600"
str_IMAGE_DEFAULT_SLOT = "C2600-MB-1E"
object_INPUT_FILE = None
object_GNS3_PROJECT = {
    "name": args.name + " (ID: " + str(uuid4()) + ")",
    "project_id": str(uuid4()),
    "revision": 5,
    "topology": {},
    "type": "topology",
    "version": "2.0.0"
}

"""
###################################################################################################################
Defining functions.

- getGatewayInterface():
  Looks up the first available system interface with internet access.

- tupleCalculateCoordinates():
  Returns a tuple with the X and Y coordinate of a device.

- addNodeToLink():
  Adds a node (router or switch) to a link, meaning one of its two endpoints.

- writeClusterLinks():
  Write out the internal links of a cluster, influenced by the clustermode variable.

- standardizeConnection():
  Looks up if a connection definition belongs with a certain tag specified in a router cluster's connectedto variable.

- standardizeConnectionMinimal():
  Looks up if a connection definition belongs with a certain tag specified in a router cluster's connectedto variable without checking existence.
###################################################################################################################
"""
def getGatewayInterface() -> str:
    dictAddresses = psutil.net_if_addrs()
    arrayInterfaces = list(dictAddresses.keys())

    for strInterface in arrayInterfaces:
        strAddress = dictAddresses[strInterface][1].address
        ping_process = subprocess.Popen(["ping", "-n", "1", "-S", strAddress, "8.8.8.8"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ping_process.wait()
        if ping_process.returncode == 0:
            return strInterface
    
    print("You are trying to create a gateway while your own system doesn't seem to have access to the internet. Aborting.")
    exit()

def tupleCalculateCoordinates() -> tuple:
    return (0, 0)

def addNodeToLink(tupleDesiredLink, objectLinkConstruction, arrayDesiredRouterClusters, arrayDesiredSwitchClusters) -> None:
    for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
        for arrayDesiredRouter in arrayDesiredRouterCluster[1]:
            if (arrayDesiredRouter[0] == tupleDesiredLink[0]):
                if (arrayDesiredRouter[1] > 16):
                    print("One of your router clusters exceeds the 16-port limit on one of its devices. Aborting.") # Depends on NM-16ESW's 16 slot limit
                    exit()

                objectLinkConstruction["nodes"].append({"adapter_number": tupleDesiredLink[1], "port_number": arrayDesiredRouter[1], "node_id": arrayDesiredRouter[0]})
                arrayDesiredRouter[1] += 1
                break
    
    for arrayDesiredSwitchCluster in arrayDesiredSwitchClusters:
        for arrayDesiredSwitch in arrayDesiredSwitchCluster[1]:
            if (arrayDesiredSwitch[0] == tupleDesiredLink[0]):
                if (arrayDesiredSwitch[1] > 16):
                    print("One of your switch clusters exceeds the 16-port limit on one of its devices. Aborting.") # Arbitrarily set to 16 to equal routers
                    exit()

                objectLinkConstruction["nodes"].append({"adapter_number": tupleDesiredLink[1], "port_number": arrayDesiredSwitch[1], "node_id": arrayDesiredSwitch[0]})
                arrayDesiredSwitch[1] += 1
                break

def writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, arrayDesiredRouterClusters, arrayDesiredSwitchClusters, objectTemporaryGNS3Topology) -> None:
    for tupleDesiredLink in arrayDesiredLinks:
        objectLinkConstruction = copy.deepcopy(objectGNS3LinkScaffold)
        objectLinkConstruction["link_id"] = str(uuid4())
        addNodeToLink(tupleDesiredLink[0], objectLinkConstruction, arrayDesiredRouterClusters, arrayDesiredSwitchClusters)
        addNodeToLink(tupleDesiredLink[1], objectLinkConstruction, arrayDesiredRouterClusters, arrayDesiredSwitchClusters)
        objectTemporaryGNS3Topology["links"].append(objectLinkConstruction)

def standardizeConnection(connection, objectConnections, objectRouterCluster) -> dict:
    returnValue = connection

    booleanFoundConnection = False
    for objectConnection in objectConnections:
        if (objectConnection["tag"] == connection):
            returnValue = objectConnection
            booleanFoundConnection = True
            break
    if (booleanFoundConnection == False):
        print("Router cluster with tag '" + objectRouterCluster["tag"] + "' is referring to a non-existent connection. Aborting.")
        exit()

    return returnValue

def standardizeConnectionMinimal(connection, objectConnections) -> dict:
    returnValue = connection

    for objectConnection in objectConnections:
        if (objectConnection["tag"] == connection):
            returnValue = objectConnection
            break

    return returnValue

"""
###################################################################################################################
Setting up input file parsing.

This section checks whether or not the input .yml file is correctly formatted.
###################################################################################################################
"""
with open(args.input, "r") as stream:
    try:
        object_INPUT_FILE = yaml.safe_load(stream)
    except yaml.YAMLError as err:
        print("Invalid .yml file. There is a syntax error.")
        exit()

objectDesiredSchemaBase = Schema({
    "tag": str,    
    Optional("cables", default=1): And(int, lambda value: 1 <= value <= 3)
    #Optional("ipclass", default="A"): Or("A", "B", "C"),
    #Optional("ipsummary", default="auto"): Or("auto", Regex("^(?:\d{1,3}\.){3}\d{1,3}\/(?:[1-9]|[1-2][0-9]|3[0-2])$"))
})

objectDesiredSchemaSwitchCluster = Schema({**objectDesiredSchemaBase.schema, **Schema({
    Optional("amount", default=1): And(int, lambda value: 1 <= value <= 255),
    Optional("clustermode", default="full"): Or("full", "loop", "line", "hubspoke"),
    Optional("connectionshift", default=0): And(int, lambda value: 1 <= value <= 255)
}).schema})

objectDesiredSchemaConnection = Schema({**objectDesiredSchemaBase.schema, **Schema({
    Optional("connectionmode", default="single"): Or("single", "full", "parallel"),
    Optional("shiftable", default=True): bool,
    Optional("switches", default=None): objectDesiredSchemaSwitchCluster
}).schema})

objectDesiredSchemaRouterCluster = Schema({**objectDesiredSchemaSwitchCluster.schema, **Schema({
    Optional("routing", default="static"): Or("static"),
    Optional("gateway", default=False): bool,
    Optional("connectedto", default=None): [Or(str, objectDesiredSchemaConnection)]
}).schema})

objectDesiredSchemaTotal = Schema({
    "input": {
        "routers": [objectDesiredSchemaRouterCluster],
        Optional("connections", default=None): [objectDesiredSchemaConnection]
    }
})

try:
    objectDesiredSchemaTotal.validate(object_INPUT_FILE)
    print("Input file is valid! Moving on.")
except SchemaError as err:
    print("Invalid input file. Did you follow the schema correctly? Check the following:\n\n" + str(err))
    exit()

"""
###################################################################################################################
Building the topology in-memory.

This is where the input file actually gets translated into a network design using the NetworkNarcotic algorithm.
###################################################################################################################
"""
objectRouterClusters = objectDesiredSchemaTotal.validate(object_INPUT_FILE).get("input").get("routers")
objectSwitchClusters = []
objectConnections = objectDesiredSchemaTotal.validate(object_INPUT_FILE).get("input").get("connections")
objectTemporaryGNS3Topology = {
    "computes": [],
    "drawings": [],
    "links": [],
    "nodes": []
}
objectGNS3RouterNodeScaffold = {
    "compute_id": "local",
    "name": None,
    "node_id": None,
    "node_type": "dynamips",
    "x": None,
    "y": None,
    "symbol": ":/symbols/router.svg",
    "properties": {
        "image": str_IMAGE,
        "image_md5sum": str_IMAGE_MD5,
        "platform": str_IMAGE_PLATFORM,
        "ram": 160,
        "dynamips_id": None,
        "slot0": str_IMAGE_DEFAULT_SLOT,
        "slot1": "NM-16ESW",
    }
}
objectGNS3CloudNodeScaffold = {
    "compute_id": "local",
    "name": None,
    "node_id": None,
    "node_type": "cloud",
    "x": None,
    "y": None,
    "symbol": ":/symbols/cloud.svg",
    "properties": {
        "interfaces": [
            {
                "name": getGatewayInterface(),
                "special": True,
                "type": "ethernet"
            },
        ],
        "ports_mapping": [
            {
                "interface": getGatewayInterface(),
                "name": getGatewayInterface(),
                "port_number": 0,
                "type": "ethernet"
            }
        ]
    }
}
objectGNS3SwitchNodeScaffold = {
    "compute_id": "local",
    "name": None,
    "node_id": None,
    "node_type": "ethernet_switch",
    "x": None,
    "y": None,
    "symbol": ":/symbols/ethernet_switch.svg",
    "properties": {
        "ports_mapping": [
            {
                "name": "Ethernet0",
                "port_number": 0,
                "type": "access",
                "vlan": 1
            },
            {
                "name": "Ethernet1",
                "port_number": 1,
                "type": "access",
                "vlan": 1
            },
            {
                "name": "Ethernet2",
                "port_number": 2,
                "type": "access",
                "vlan": 1
            },
            {
                "name": "Ethernet3",
                "port_number": 3,
                "type": "access",
                "vlan": 1
            },
            {
                "name": "Ethernet4",
                "port_number": 4,
                "type": "access",
                "vlan": 1
            },
            {
                "name": "Ethernet5",
                "port_number": 5,
                "type": "access",
                "vlan": 1
            },
            {
                "name": "Ethernet6",
                "port_number": 6,
                "type": "access",
                "vlan": 1
            },
            {
                "name": "Ethernet7",
                "port_number": 7,
                "type": "access",
                "vlan": 1
            },
            {
                "ethertype": "",
                "name": "Ethernet8",
                "port_number": 8,
                "type": "access",
                "vlan": 1
            },
            {
                "ethertype": "",
                "name": "Ethernet9",
                "port_number": 9,
                "type": "access",
                "vlan": 1
            },
            {
                "ethertype": "",
                "name": "Ethernet10",
                "port_number": 10,
                "type": "access",
                "vlan": 1
            },
            {
                "ethertype": "",
                "name": "Ethernet11",
                "port_number": 11,
                "type": "access",
                "vlan": 1
            },
            {
                "ethertype": "",
                "name": "Ethernet12",
                "port_number": 12,
                "type": "access",
                "vlan": 1
            },
            {
                "ethertype": "",
                "name": "Ethernet13",
                "port_number": 13,
                "type": "access",
                "vlan": 1
            },
            {
                "ethertype": "",
                "name": "Ethernet14",
                "port_number": 14,
                "type": "access",
                "vlan": 1
            },
            {
                "ethertype": "",
                "name": "Ethernet15",
                "port_number": 15,
                "type": "access",
                "vlan": 1
            }
        ]
    }
}
objectGNS3LinkScaffold = {
    "filters": {},
    "link_id": None,
    "link_style": {},
    "nodes": [],
    "suspend": False
}

# Collect switch clusters
for objectConnection in objectConnections:
    if (objectConnection["switches"] != None):
        objectSwitchClusters.append(objectConnection["switches"])

# Handle switch clusters
arrayDesiredSwitchClusters = [] # Holds per cluster tag an array of arrays, the latter containing a node_id and currently available port number
for objectSwitchCluster in objectSwitchClusters:
    for intCurrent in range(objectSwitchCluster["amount"]):
        # For each switch cluster, mutiplied by the "amount" in that cluster, create a switch
        objectSwitchNodeConstruction = copy.deepcopy(objectGNS3SwitchNodeScaffold)
        objectSwitchNodeConstruction["name"] = objectSwitchCluster["tag"] + "-id" + str(intCurrent + 1)
        objectSwitchNodeConstruction["node_id"] = str(uuid4())
        objectSwitchNodeConstruction["x"] = tupleCalculateCoordinates()[0] # TODO
        objectSwitchNodeConstruction["y"] = tupleCalculateCoordinates()[1] # TODO

        # Add the switch router to the topology
        booleanSwitchClusterIsKnown = False
        for arrayDesiredSwitchCluster in arrayDesiredSwitchClusters:
            if (arrayDesiredSwitchCluster[0] == objectSwitchCluster["tag"]):
                booleanSwitchClusterIsKnown = True
                break
        
        if (booleanSwitchClusterIsKnown == False):
            arrayDesiredSwitchClusters.append([objectSwitchCluster["tag"], [[objectSwitchNodeConstruction["node_id"], 0]]])
        else:
            for arrayDesiredSwitchCluster in arrayDesiredSwitchClusters:
                if (arrayDesiredSwitchCluster[0] == objectSwitchCluster["tag"]):
                    arrayDesiredSwitchCluster[1].append([objectSwitchNodeConstruction["node_id"], 0])

        objectTemporaryGNS3Topology["nodes"].append(objectSwitchNodeConstruction)
       
    # Do the magic
    if (objectSwitchCluster["amount"] > 1):
        # For each switch cluster, apply cables in case necessary
        match objectSwitchCluster["clustermode"]:
            case "full":
                # Define the links
                arrayDesiredLinks = []
                for arrayDesiredSwitchCluster in arrayDesiredSwitchClusters:
                    if (arrayDesiredSwitchCluster[0] == objectSwitchCluster["tag"]):
                        for arrayDesiredSwitchSTART in arrayDesiredSwitchCluster[1]:
                            for arrayDesiredSwitchEND in arrayDesiredSwitchCluster[1]:
                                if (arrayDesiredSwitchSTART[0] != arrayDesiredSwitchEND[0]):
                                    if (not ((arrayDesiredSwitchEND[0], 0), (arrayDesiredSwitchSTART[0], 0)) in arrayDesiredLinks):
                                        for intCurrent in range (objectSwitchCluster["cables"]):
                                            arrayDesiredLinks.append(((arrayDesiredSwitchSTART[0], 0), (arrayDesiredSwitchEND[0], 0)))
                        break

                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, [], arrayDesiredSwitchClusters, objectTemporaryGNS3Topology)
            case "loop":
                # Define the links
                arrayDesiredLinks = []
                stringEndPoint = arrayDesiredSwitchCluster[1]
                intCounter = 0
                for arrayDesiredSwitchCluster in arrayDesiredSwitchClusters:
                    if (arrayDesiredSwitchCluster[0] == objectSwitchCluster["tag"]):
                        for stringNode in arrayDesiredSwitchCluster[1]:
                            if (intCounter != len(arrayDesiredSwitchCluster[1])):
                                for intCurrent in range (objectSwitchCluster["cables"]):
                                    arrayDesiredLinks.append(((stringNode[0], 0), (arrayDesiredSwitchCluster[1][(intCounter + 1) % len(arrayDesiredSwitchCluster[1])][0], 0)))
                                intCounter += 1
                        break
                
                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, [], arrayDesiredSwitchClusters, objectTemporaryGNS3Topology)
            case "line":
                # Define the links
                arrayDesiredLinks = []
                stringEndPoint = arrayDesiredSwitchCluster[1]
                intCounter = 0
                for arrayDesiredSwitchCluster in arrayDesiredSwitchClusters:
                    if (arrayDesiredSwitchCluster[0] == objectSwitchCluster["tag"]):
                        for stringNode in arrayDesiredSwitchCluster[1]:
                            if (intCounter != len(arrayDesiredSwitchCluster[1]) -1): # Notice the -1; the "cut" in the loop
                                for intCurrent in range (objectSwitchCluster["cables"]):
                                    arrayDesiredLinks.append(((stringNode[0], 0), (arrayDesiredSwitchCluster[1][(intCounter + 1) % len(arrayDesiredSwitchCluster[1])][0], 0)))
                                intCounter += 1
                        break

                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, [], arrayDesiredSwitchClusters, objectTemporaryGNS3Topology)
            case "hubspoke":
                # Define the links
                arrayDesiredLinks = []
                for arrayDesiredSwitchCluster in arrayDesiredSwitchClusters:
                    if (arrayDesiredSwitchCluster[0] == objectSwitchCluster["tag"]):
                        stringHubNode = arrayDesiredSwitchCluster[1][0][0]
                        for stringNode in arrayDesiredSwitchCluster[1]:
                            if (stringNode[0] != stringHubNode):
                                for intCurrent in range (objectSwitchCluster["cables"]):
                                    arrayDesiredLinks.append(((stringHubNode, 0), (stringNode[0], 0)))
                        break

                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, [], arrayDesiredSwitchClusters, objectTemporaryGNS3Topology)

# Handle router clusters
arrayDesiredRouterClusters = [] # Holds per cluster tag an array of arrays, the latter containing a node_id and currently available port number
for objectRouterCluster in objectRouterClusters:
    for intCurrent in range(objectRouterCluster["amount"]):
        # For each router cluster, mutiplied by the "amount" in that cluster, create a router
        objectRouterNodePropertiesConstruction = copy.deepcopy(objectGNS3RouterNodeScaffold["properties"])
        objectRouterNodePropertiesConstruction["dynamips_id"] = uuid4().int
        objectRouterNodeConstruction = copy.deepcopy(objectGNS3RouterNodeScaffold)
        objectRouterNodeConstruction["properties"] = objectRouterNodePropertiesConstruction
        objectRouterNodeConstruction["name"] = objectRouterCluster["tag"] + "-id" + str(intCurrent + 1)
        objectRouterNodeConstruction["node_id"] = str(uuid4())
        objectRouterNodeConstruction["x"] = tupleCalculateCoordinates()[0] # TODO
        objectRouterNodeConstruction["y"] = tupleCalculateCoordinates()[1] # TODO

        # Add the created router to the topology
        booleanRouterClusterIsKnown = False
        for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
            if (arrayDesiredRouterCluster[0] == objectRouterCluster["tag"]):
                booleanRouterClusterIsKnown = True
                break
        
        if (booleanRouterClusterIsKnown == False):
            arrayDesiredRouterClusters.append([objectRouterCluster["tag"], [[objectRouterNodeConstruction["node_id"], 0]]])
        else:
            for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                if (arrayDesiredRouterCluster[0] == objectRouterCluster["tag"]):
                    arrayDesiredRouterCluster[1].append([objectRouterNodeConstruction["node_id"], 0])

        objectTemporaryGNS3Topology["nodes"].append(objectRouterNodeConstruction)
       
    # Handle gateways
    if (objectRouterCluster["gateway"] == True):
        strCloudNode = str(uuid4())

        # Create the cloud
        objectCloudNodeConstruction = copy.deepcopy(objectGNS3CloudNodeScaffold)
        objectCloudNodeConstruction["name"] = "INTERNET-" + objectRouterCluster["tag"]
        objectCloudNodeConstruction["node_id"] = strCloudNode
        objectCloudNodeConstruction["x"] = tupleCalculateCoordinates()[0] # TODO
        objectCloudNodeConstruction["y"] = tupleCalculateCoordinates()[1] # TODO
        objectTemporaryGNS3Topology["nodes"].append(objectCloudNodeConstruction)

        # Create the link
        tupleDesiredLink = None
        for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
            if (arrayDesiredRouterCluster[0] == objectRouterCluster["tag"]):
                tupleDesiredLink = (strCloudNode, arrayDesiredRouterCluster[1][0][0])

        objectLinkConstruction = copy.deepcopy(objectGNS3LinkScaffold)
        objectLinkConstruction["link_id"] = str(uuid4())
        objectLinkConstruction["nodes"].append({"adapter_number": 0, "port_number": 0, "node_id": strCloudNode}) # No risk on exceeding port limit
        addNodeToLink((tupleDesiredLink[1], 1), objectLinkConstruction, arrayDesiredRouterClusters, arrayDesiredSwitchClusters)
        objectTemporaryGNS3Topology["links"].append(objectLinkConstruction)
    
    # Do the magic
    if (objectRouterCluster["amount"] > 1):
        # For each router cluster, apply cables in case necessary
        match objectRouterCluster["clustermode"]:
            case "full":
                # Define the links
                arrayDesiredLinks = []
                for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                    if (arrayDesiredRouterCluster[0] == objectRouterCluster["tag"]):
                        for arrayDesiredRouterSTART in arrayDesiredRouterCluster[1]:
                            for arrayDesiredRouterEND in arrayDesiredRouterCluster[1]:
                                if (arrayDesiredRouterSTART[0] != arrayDesiredRouterEND[0]):
                                    if (not ((arrayDesiredRouterEND[0], 1), (arrayDesiredRouterSTART[0], 1)) in arrayDesiredLinks):
                                        for intCurrent in range (objectRouterCluster["cables"]):
                                            arrayDesiredLinks.append(((arrayDesiredRouterSTART[0], 1), (arrayDesiredRouterEND[0], 1)))
                        break

                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, arrayDesiredRouterClusters, arrayDesiredSwitchClusters, objectTemporaryGNS3Topology)
            case "loop":
                # Define the links
                arrayDesiredLinks = []
                stringEndPoint = arrayDesiredRouterCluster[1]
                intCounter = 0
                for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                    if (arrayDesiredRouterCluster[0] == objectRouterCluster["tag"]):
                        for stringNode in arrayDesiredRouterCluster[1]:
                            if (intCounter != len(arrayDesiredRouterCluster[1])):
                                for intCurrent in range (objectRouterCluster["cables"]):
                                    arrayDesiredLinks.append(((stringNode[0], 1), (arrayDesiredRouterCluster[1][(intCounter + 1) % len(arrayDesiredRouterCluster[1])][0], 1)))
                                intCounter += 1
                        break
                
                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, arrayDesiredRouterClusters, arrayDesiredSwitchClusters, objectTemporaryGNS3Topology)
            case "line":
                # Define the links
                arrayDesiredLinks = []
                stringEndPoint = arrayDesiredRouterCluster[1]
                intCounter = 0
                for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                    if (arrayDesiredRouterCluster[0] == objectRouterCluster["tag"]):
                        for stringNode in arrayDesiredRouterCluster[1]:
                            if (intCounter != len(arrayDesiredRouterCluster[1]) -1): # Notice the -1; the "cut" in the loop
                                for intCurrent in range (objectRouterCluster["cables"]):
                                    arrayDesiredLinks.append(((stringNode[0], 1), (arrayDesiredRouterCluster[1][(intCounter + 1) % len(arrayDesiredRouterCluster[1])][0], 1)))
                                intCounter += 1
                        break

                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, arrayDesiredRouterClusters, arrayDesiredSwitchClusters, objectTemporaryGNS3Topology)
            case "hubspoke":
                # Define the links
                arrayDesiredLinks = []
                for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                    if (arrayDesiredRouterCluster[0] == objectRouterCluster["tag"]):
                        stringHubNode = arrayDesiredRouterCluster[1][0][0]
                        for stringNode in arrayDesiredRouterCluster[1]:
                            if (stringNode[0] != stringHubNode):
                                for intCurrent in range (objectRouterCluster["cables"]):
                                    arrayDesiredLinks.append(((stringHubNode, 1), (stringNode[0], 1)))
                        break

                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, arrayDesiredRouterClusters, arrayDesiredSwitchClusters, objectTemporaryGNS3Topology)

# Find connection elements
arrayConnectionElements = [] # Holds per connection tag an array of involved router clusters
for objectRouterCluster in objectRouterClusters:
    if (objectRouterCluster["connectedto"] != None):
        arrayClusterConnections = []
        for connection in objectRouterCluster["connectedto"]:
            objectDesiredConnection = standardizeConnection(connection, objectConnections, objectRouterCluster)

            # Check if the connection tag hasn't been seen before in this router cluster
            for arrayClusterConnection in arrayClusterConnections:
                if (arrayClusterConnection == objectDesiredConnection["tag"]):
                    print("Router cluster with tag " + objectRouterCluster["tag"] + " is referring to the same connection more than once. Aborting.")
                    exit()

            booleanConnectionIsKnown = False
            for arrayConnectionElement in arrayConnectionElements:
                if (arrayConnectionElement[0] == objectDesiredConnection["tag"]):
                    booleanConnectionIsKnown = True
                    break
            if (booleanConnectionIsKnown == False):
                arrayConnectionElements.append([objectDesiredConnection["tag"], [objectRouterCluster["tag"]]])

            # Find all other router clusters that need this connection, if any
            for objectRouterClusterNest in objectRouterClusters:
                if (objectRouterClusterNest["tag"] != objectRouterCluster["tag"] and objectRouterClusterNest["connectedto"] != None):
                    for connectionNest in objectRouterClusterNest["connectedto"]:
                        objectDesiredConnectionNest = standardizeConnection(connectionNest, objectConnections, objectRouterClusterNest)
                        if (objectDesiredConnectionNest["tag"] == objectDesiredConnection["tag"]):
                            booleanConnectionIsKnown = False
                            for arrayConnectionElement in arrayConnectionElements:
                                if (arrayConnectionElement[0] == objectDesiredConnection["tag"]):
                                    booleanConnectionIsKnown = True
                                    break

                            for arrayConnectionElement in arrayConnectionElements:
                                if (arrayConnectionElement[0] == objectDesiredConnection["tag"]):
                                    if (objectRouterCluster["tag"] not in arrayConnectionElement[1]):
                                        arrayConnectionElement[1].append(objectRouterCluster["tag"])
                                    if (objectRouterClusterNest["tag"] not in arrayConnectionElement[1]):
                                        arrayConnectionElement[1].append(objectRouterClusterNest["tag"])

# Define connections
arrayDesiredConnections = [] # Holds per connection tag an array of tuples, the latter containing two tuples with a node_id and an adapter number
for arrayConnectionElement in arrayConnectionElements:
    objectDesiredConnection = standardizeConnectionMinimal(arrayConnectionElement[0], objectConnections)
    arrayInvolvedSwitchCluster = None

    # Check for presence of switch cluster in case necessary
    if (objectDesiredConnection["switches"] == None and len(arrayConnectionElement[1]) > 2):
        print("Hooking more than two router clusters to a connection (" + objectDesiredConnection["tag"] + ") requires a switch cluster. Aborting.")
        exit()

    for arrayDesiredSwitchCluster in arrayDesiredSwitchClusters:
        if (objectDesiredConnection["switches"] != None and arrayDesiredSwitchCluster[0] == objectDesiredConnection["switches"]["tag"]):
            arrayInvolvedSwitchCluster = arrayDesiredSwitchCluster

    # Do the magic
    match objectDesiredConnection["connectionmode"]:
        case "single":
            # Define the links
            arrayDesiredLinks = []

            arrayRouterPoints = []
            arraySwitchPoints = []
            for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                arrayRouterShifted = deque(arrayDesiredRouterCluster[1])
                for objectRouterCluster in objectRouterClusters:
                    for stringRouterTag in arrayConnectionElement[1]:
                        if (objectRouterCluster["tag"] == arrayDesiredRouterCluster[0] == stringRouterTag and objectDesiredConnection["shiftable"] == True):
                            arrayRouterShifted.rotate(-objectRouterCluster["connectionshift"])
                            arrayRouterPoints.append([objectRouterCluster["tag"], arrayRouterShifted[0]])
                
            for objectSwitchCluster in objectSwitchClusters:
                arraySwitchShifted = deque(arrayInvolvedSwitchCluster[1])
                if (objectSwitchCluster["tag"] == arrayInvolvedSwitchCluster[0] and objectDesiredConnection["shiftable"] == True):
                    arraySwitchShifted.rotate(-objectSwitchCluster["connectionshift"])
                    arraySwitchPoints.append(arraySwitchShifted[0])
                    break
                
            # Put the switch cluster inbetween in case necessary
            if (arrayInvolvedSwitchCluster != None):
                for arrayRouterPoint in arrayRouterPoints:
                    for arrayDesiredSwitch in arraySwitchPoints:
                        arrayDesiredLinks.append(((arrayRouterPoint[1][0], 1), (arrayDesiredSwitch[0], 0)))
            else:
                for arrayRouterPointSTART in arrayRouterPoints:
                    for arrayRouterPointEND in arrayRouterPoints:
                        if (arrayRouterPointSTART[0] != arrayRouterPointEND[0]):
                            if (not (arrayRouterPointEND[1][0], arrayRouterPointSTART[1][0]) in arrayDesiredLinks):
                                arrayDesiredLinks.append(((arrayRouterPointSTART[1][0], 1), (arrayRouterPointEND[1][0], 1)))

            # Append the links
            arrayDesiredConnections.append([arrayConnectionElement[0], arrayDesiredLinks])
        case "full":
            # Define the links
            arrayDesiredLinks = []
            arrayStartPoints = []
            arrayEndPoints = []
            for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                if (arrayDesiredRouterCluster[0] == arrayConnectionElement[1][0]):
                    for arrayDesiredRouter in arrayDesiredRouterCluster[1]:
                        arrayStartPoints.append(arrayDesiredRouter)
                if (arrayDesiredRouterCluster[0] == arrayConnectionElement[1][1]):
                    for arrayDesiredRouter in arrayDesiredRouterCluster[1]:
                        arrayEndPoints.append(arrayDesiredRouter)
            for arrayDesiredRouterSTART in arrayStartPoints:
                for arrayDesiredRouterEND in arrayEndPoints:
                    if (arrayDesiredRouterSTART[0] != arrayDesiredRouterEND[0]):
                        if (not (arrayDesiredRouterEND[0], arrayDesiredRouterSTART[0]) in arrayDesiredLinks):
                            arrayDesiredLinks.append(((arrayDesiredRouterSTART[0], 1), (arrayDesiredRouterEND[0], 1)))

            # Append the links
            arrayDesiredConnections.append([arrayConnectionElement[0], arrayDesiredLinks])
        case "parallel":
            # Define the links
            arrayDesiredLinks = []

            intClusterLengthA = None
            intClusterLengthB = None
            for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                if (arrayDesiredRouterCluster[0] == arrayConnectionElement[1][0]):
                    intClusterLengthA = len(arrayDesiredRouterCluster[1])
                if (arrayDesiredRouterCluster[0] == arrayConnectionElement[1][1]):
                    intClusterLengthB = len(arrayDesiredRouterCluster[1])

            arrayStartPoints = []
            arrayEndPoints = []
            for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                arrayShifted = deque(arrayDesiredRouterCluster[1])
                for objectRouterCluster in objectRouterClusters:
                    if (objectRouterCluster["tag"] == arrayDesiredRouterCluster[0] and objectDesiredConnection["shiftable"] == True):
                        arrayShifted.rotate(-objectRouterCluster["connectionshift"])

                intCounter = 0
                if (arrayDesiredRouterCluster[0] == arrayConnectionElement[1][0]):
                    for arrayDesiredRouter in arrayShifted:
                        if (intCounter < min(intClusterLengthA, intClusterLengthB)):
                            arrayStartPoints.append(arrayDesiredRouter[0])
                            intCounter += 1
                if (arrayDesiredRouterCluster[0] == arrayConnectionElement[1][1]):
                    for arrayDesiredRouter in arrayShifted:
                        if (intCounter < min(intClusterLengthA, intClusterLengthB)):
                            arrayEndPoints.append(arrayDesiredRouter[0])
                            intCounter += 1
            for intCurrent in range(min(intClusterLengthA, intClusterLengthB)):
                arrayDesiredLinks.append(((arrayStartPoints[intCurrent], 1), (arrayEndPoints[intCurrent], 1)))
                
            # Append the links
            arrayDesiredConnections.append([arrayConnectionElement[0], arrayDesiredLinks])

# Apply connections
for arrayDesiredConnection in arrayDesiredConnections:
    for objectConnection in objectConnections:
        if (objectConnection["tag"] == arrayDesiredConnection[0]):
            for tupleDesiredLink in arrayDesiredConnection[1]:
                for intCurrent in range(objectConnection["cables"]):
                    #print(tupleDesiredLink)
                    objectLinkConstruction = copy.deepcopy(objectGNS3LinkScaffold)
                    objectLinkConstruction["link_id"] = str(uuid4())
                    addNodeToLink(tupleDesiredLink[0], objectLinkConstruction, arrayDesiredRouterClusters, arrayDesiredSwitchClusters)
                    addNodeToLink(tupleDesiredLink[1], objectLinkConstruction, arrayDesiredRouterClusters, arrayDesiredSwitchClusters)
                    objectTemporaryGNS3Topology["links"].append(objectLinkConstruction)

# Handle coordinates
# TODO
# graphTest = nx.Graph()

print("Done building in-memory topology.")

"""
###################################################################################################################
Building the .gns3 file.

This is where the in-memory topology is converted into a usable .gns3 file.
###################################################################################################################
"""
object_GNS3_PROJECT["topology"] = objectTemporaryGNS3Topology
file = open(args.output, "a")
file.truncate(0)
file.write(json.dumps(object_GNS3_PROJECT, indent=4))
file.close()

print("Done building .gns3 file. Open it in GNS3, but make sure the following router image is installed: " + str_IMAGE)
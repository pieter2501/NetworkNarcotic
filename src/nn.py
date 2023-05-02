import argparse             # Required for argument passing
import yaml                 # Required for reading input files
import networkx as nx       # Required for drawing topologies
import json                 # Required for writing output files
import copy                 # Required for creating shallow copies in for loops
from schema import Schema, SchemaError, Optional, And, Or, Regex # Required for reading input files
from uuid import uuid4      # Required for generating GNS3-compatible randoms

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

- tupleCalculateCoordinates():
  Returns a tuple with the X and Y coordinate of a device.

- addNodeToLink():
  Adds a node (router or switch) to a link, meaning one of its two endpoints.

- writeClusterLinks():
  Write out the internal links of a cluster, influenced by the clustermode variable.

- standardizeConnection():
  Looks up if a connection definition belongs with a certain tag specified in a router cluster's connectedto variable.
###################################################################################################################
"""
def tupleCalculateCoordinates() -> tuple:
    return (0, 0)

def addNodeToLink(stringNode, objectLinkConstruction, arrayDesiredRouterClusters) -> None:
    for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
        for arrayDesiredRouter in arrayDesiredRouterCluster[1]:
            if (arrayDesiredRouter[0] == stringNode):
                if (arrayDesiredRouter[1] > 16):
                    print("One of your clusters exceeds the 16-port limit on one of its devices. Aborting.") # Depends on NM-16ESW's 16 slot limit
                    exit()

                objectLinkConstruction["nodes"].append({"adapter_number": 1, "port_number": arrayDesiredRouter[1], "node_id": arrayDesiredRouter[0]})
                arrayDesiredRouter[1] += 1
                break

def writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, arrayDesiredRouterClusters, objectTemporaryGNS3Topology) -> None:
    for tupleDesiredLink in arrayDesiredLinks:
        objectLinkConstruction = copy.deepcopy(objectGNS3LinkScaffold)
        objectLinkConstruction["link_id"] = str(uuid4())
        addNodeToLink(tupleDesiredLink[0], objectLinkConstruction, arrayDesiredRouterClusters)
        addNodeToLink(tupleDesiredLink[1], objectLinkConstruction, arrayDesiredRouterClusters)
        objectTemporaryGNS3Topology["links"].append(objectLinkConstruction)

def standardizeConnection(connection, objectConnections, objectRouterCluster) -> dict:
    returnValue = connection;
    if (type(connection) is str):
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
    Optional("cables", default=1): And(int, lambda value: 1 <= value <= 3),
    Optional("ipclass", default="A"): Or("A", "B", "C"),
    Optional("ipsummary", default="auto"): Or("auto", Regex("^(?:\d{1,3}\.){3}\d{1,3}\/(?:[1-9]|[1-2][0-9]|3[0-2])$"))
})

objectDesiredSchemaSwitchCluster = Schema({**objectDesiredSchemaBase.schema, **Schema({
    Optional("amount", default=1): And(int, lambda value: 1 <= value <= 255),
    Optional("clustermode", default="full"): Or("full", "loop", "line", "hubspoke"),
    Optional("connectionshift", default=0): And(int, lambda value: 1 <= value <= 255)
}).schema})

objectDesiredSchemaConnection = Schema({**objectDesiredSchemaBase.schema, **Schema({
    Optional("connectionmode", default="single"): Or("single", "full", "seek", "parallel", "spread"),
    Optional("shiftable", default=True): bool,
    Optional("switches", default=None): [objectDesiredSchemaSwitchCluster]
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
objectGNS3SwitchNodeScaffold = {
    "compute_id": "local",
    "name": None,
    "node_id": None,
    "node_type": "ethernet_switch",
    "x": None,
    "y": None,
    "symbol": ":/symbols/ethernet_switch.svg"
}
objectGNS3LinkScaffold = {
    "filters": {},
    "link_id": None,
    "link_style": {},
    "nodes": [],
    "suspend": False
}

# Handle the routers
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
                                    if (not (arrayDesiredRouterEND[0], arrayDesiredRouterSTART[0]) in arrayDesiredLinks):
                                        for intCurrent in range (objectRouterCluster["cables"]):
                                            arrayDesiredLinks.append((arrayDesiredRouterSTART[0], arrayDesiredRouterEND[0]))
                        break

                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, arrayDesiredRouterClusters, objectTemporaryGNS3Topology)
            case "loop":
                # Define the links
                arrayDesiredLinks = []
                stringEndPoint = arrayDesiredRouterCluster[1]
                intCounter = 0
                for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                    if (arrayDesiredRouterCluster[0] == objectRouterCluster["tag"]):
                        for stringNode in arrayDesiredRouterCluster[1]:
                            print(stringNode)
                            if (intCounter != len(arrayDesiredRouterCluster[1])):
                                for intCurrent in range (objectRouterCluster["cables"]):
                                    arrayDesiredLinks.append((stringNode[0], arrayDesiredRouterCluster[1][(intCounter + 1) % len(arrayDesiredRouterCluster[1])][0]))
                                intCounter += 1
                        break
                
                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, arrayDesiredRouterClusters, objectTemporaryGNS3Topology)
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
                                    arrayDesiredLinks.append((stringNode[0], arrayDesiredRouterCluster[1][(intCounter + 1) % len(arrayDesiredRouterCluster[1])][0]))
                                intCounter += 1
                        break

                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, arrayDesiredRouterClusters, objectTemporaryGNS3Topology)
            case "hubspoke":
                # Define the links
                arrayDesiredLinks = []
                for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                    if (arrayDesiredRouterCluster[0] == objectRouterCluster["tag"]):
                        stringHubNode = arrayDesiredRouterCluster[1][0][0]
                        for stringNode in arrayDesiredRouterCluster[1]:
                            if (stringNode[0] != stringHubNode):
                                for intCurrent in range (objectRouterCluster["cables"]):
                                    arrayDesiredLinks.append((stringHubNode, stringNode[0]))
                        break

                # Write the links
                writeClusterLinks(arrayDesiredLinks, objectGNS3LinkScaffold, arrayDesiredRouterClusters, objectTemporaryGNS3Topology)

# Handle connections
arrayDesiredConnections = []
for objectRouterCluster in objectRouterClusters:
    arrayClusterConnections = []
    if (objectRouterCluster["connectedto"] != None):
        for connection in objectRouterCluster["connectedto"]:
            objectDesiredConnection = standardizeConnection(connection, objectConnections, objectRouterCluster)
            
            for arrayClusterConnection in arrayClusterConnections:
                if (arrayClusterConnection == objectDesiredConnection["tag"]):
                    print("Router cluster with tag " + objectRouterCluster["tag"] + " is referring to the same connection more than once. Aborting.")
                    exit()

            arrayClusterConnections.append(objectDesiredConnection["tag"])

            match objectDesiredConnection["connectionmode"]:
                case "single":
                    booleanConnectionIsKnown = False
                    for arrayDesiredConnection in arrayDesiredConnections:
                        if (arrayDesiredConnection[0] == objectDesiredConnection["tag"]):
                            booleanConnectionIsKnown = True
                            break

                    stringFirstRouter = None
                    for arrayDesiredRouterCluster in arrayDesiredRouterClusters:
                        if (arrayDesiredRouterCluster[0] == objectRouterCluster["tag"]):
                            stringFirstRouter = arrayDesiredRouterCluster[1][0]
                            break

                    if (booleanConnectionIsKnown == False):
                        arrayDesiredConnections.append([objectDesiredConnection["tag"], [stringFirstRouter]])
                    else:
                        for arrayDesiredConnection in arrayDesiredConnections:
                            if (arrayDesiredConnection[0] == objectDesiredConnection["tag"]):
                                arrayDesiredConnection[1].append(stringFirstRouter)
                case "full":
                    temp = None
                case "seek":
                    temp = None
                case "parallel":
                    temp = None
                case "spread":
                    temp = None

# Apply the connections
for arrayDesiredConnection in arrayDesiredConnections:
    #print(arrayDesiredConnection)
    for objectConnection in objectConnections:
        if (objectConnection["tag"] == arrayDesiredConnection[0]):
            for intCurrent in range(objectConnection["cables"]):
                objectLinkConstruction = copy.deepcopy(objectGNS3LinkScaffold)
                objectLinkConstruction["link_id"] = str(uuid4())
                #addNodeToLink(arrayDesiredConnection[1][0], objectLinkConstruction, arrayFreeRouterPortPositions)
                #addNodeToLink(arrayDesiredConnection[1][1], objectLinkConstruction, arrayFreeRouterPortPositions)
                #objectTemporaryGNS3Topology["links"].append(objectLinkConstruction)
        break

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
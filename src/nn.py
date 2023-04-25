import argparse  # Required for argument passing
import yaml  # Required for reading input files
from schema import Schema, SchemaError, Optional, And, Or, Regex # Required for reading input files
import json  # Required for writing output files
from uuid import uuid4

"""
###################################################################################################################
Setting up argument parsing.

This section allows the user to specify arguments when calling the script from the CLI, such as --help.
###################################################################################################################
"""
parser = argparse.ArgumentParser(
    prog='nn.py',
    description='Converts a NetworkNarcotic input file into a .gns3 project file.',
    epilog='https://github.com/pieter2501/NetworkNarcotic')

parser.add_argument('-n', '--name', default='My NetworkNarcotic generated network', help='the name of this project')
parser.add_argument('-i', '--input', required=True, help='the input file')
parser.add_argument('-o', '--output', required=True, help='the output file')

args = parser.parse_args()

"""
###################################################################################################################
Defining global variables.

This section specifies variables that display repeated use throughout the script.
###################################################################################################################
"""
object_INPUT_FILE = None
object_MINIMAL_GNS3_PROJECT = {
    "name": args.name,
    "project_id": str(uuid4()),
    "revision": 5,
    "topology": {},
    "type": "topology",
    "version": "2.0.0"
}

"""
###################################################################################################################
Defining functions.

- test():
  A test function.
###################################################################################################################
"""
def test():
    return 'test'

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
        print('Invalid .yml file. There is a syntax error.')
        exit()

objectDesiredSchemaBase = Schema({
    "tag": And(str, error="Key 'tag' defined incorrectly."),    
    Optional("cables", default=1, error="Key 'cables' defined incorrectly."): And(int, lambda value: 1 <= value <= 3),
    Optional("cabletype", default="auto", error="Key 'cabletype' defined incorrectly."): Or("auto", "copper", "fiber", "serial"), 
    Optional("ipclass", default="A", error="Key 'ipclass' defined incorrectly."): Or("A", "B", "C"),
    Optional("ipsummary", default="auto", error="Key 'ipsummary' defined incorrectly."): Or("auto", Regex("^(?:\d{1,3}\.){3}\d{1,3}\/(?:[1-9]|[1-2][0-9]|3[0-2])$"))
})

objectDesiredSchemaSwitchCluster = Schema({**objectDesiredSchemaBase.schema, **Schema({
    Optional("amount", default=1, error="Key 'amount' defined incorrectly."): And(int, lambda value: 1 <= value <= 255),
    Optional("clustermode", default="full", error="Key 'clustermode' defined incorrectly."): Or("full", "loop", "line", "hubspoke"),
    Optional("connectionshift", default=0, error="Key 'connectionshift' defined incorrectly."): And(int, lambda value: 1 <= value <= 255)
}).schema})

objectDesiredSchemaConnection = Schema({**objectDesiredSchemaBase.schema, **Schema({
    Optional("connectionmode", default="single", error="Key 'connectionmode' defined incorrectly."): Or("single", "full", "seek", "parallel", "spread"),
    Optional("internet", default=False, error="Key 'internet' defined incorrectly."): bool,
    Optional("shiftable", default=True, error="Key 'shiftable' defined incorrectly."): bool,
    Optional("switches", default=None, error="Key 'switches' defined incorrectly."): [objectDesiredSchemaSwitchCluster]
}).schema})

objectDesiredSchemaRouterCluster = Schema({**objectDesiredSchemaSwitchCluster.schema, **Schema({
    Optional("routing", default="static", error="Key 'routing' defined incorrectly."): Or("static"),
    Optional("connectedto", default=None, error="Key 'connectedto' defined incorrectly."): [Or(str, objectDesiredSchemaConnection)]
}).schema})

objectDesiredSchemaTotal = Schema({
    "input": {
        "routers": And([objectDesiredSchemaRouterCluster], error="Key 'routers' defined incorrectly."),
        Optional("connections", default=None, error="Key 'connections' defined incorrectly."): [objectDesiredSchemaConnection]
    }
})

try:
    objectDesiredSchemaTotal.validate(object_INPUT_FILE)
    print('Input file is valid! Moving on.\n')
except SchemaError as err:
    print('Invalid input file. Did you follow the schema correctly?\n\n' + str(err))
    exit()

print('rest of program')

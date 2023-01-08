# © 2022 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.  
# This AWS Content is provided subject to the terms of the AWS Customer Agreement available at  
# http://aws.amazon.com/agreement or other written agreement between Customer and either
# Amazon Web Services, Inc. or Amazon Web Services EMEA SARL or both.

import json
import networkx as nx
import jmespath
import logging
import traceback
import re


log = logging.getLogger(__name__)

CONTACTFLOWINFO_ARN = 'Arn'
CONTACTFLOWINFO_ID = 'Id'
CONTACTFLOWINFO_NAME = 'Name'
CONTACTFLOWINFO_TYPE = 'Type'
CONTACTFLOWINFO_DESCRIPTION = 'Description'
CONTACTFLOWINFO_CONTENT = 'Content'

CONTACTFLOW_ACTIONS = 'Actions'

# set up global variables
# startNodeId = ''
endNodeIds = []
endNodeTypes = ['TransferContactToQueue', 'EndFlowExecution'
                'DisconnectParticipant', 'CreateCallbackContact']
# for initial testing - just use this one type
# endNodeTypes = ['EndFlowExecution']

class Ghostwriter:
    """Generates doc"""

    def __init__(self):
        """Initializes the object
        """
        self.contact_flows = {}         # allow for direct access rather than via model
        self.resourceIdNameMap = {}     # allow for direct access rather than via model
        self.model = {
            "resourceIdToNameMapping": self.resourceIdNameMap,
            "contactFlows": self.contact_flows,
            "contactAttributes": {},
            "lambdaFunctions": {},
            "lexBots": {}
        }
        # self.graph = nx.DiGraph()


    def process_flow(self, flow):
        """Processes a contact flow and determines the flows it is dependent on
        
        :param flow: contact flow json retrieved from an Amazon Connect instance via the API
        """

        # add the flow to the id-name mapping
        self.resourceIdNameMap[flow["Id"]] = flow["Name"]
        
        # log.debug("=> process_flow")
        # log.debug(json.dumps(flow, indent=2))
        # add in value for modules that have no type
        if "Type" not in flow:
            flow["Type"] = "CONTACT_FLOW_MODULE"
        flowNameType = "{0}||{1}".format(flow["Name"], flow["Type"])

        # flow to the contact_flows using name as index
        self.contact_flows[flowNameType] = flow

        # load the contact flow itself
        contactFlow = json.loads(flow[CONTACTFLOWINFO_CONTENT])

        # === START: process the actual flow ===
        # start loading the digraph NODES from the contact flow actions item
        graph = nx.MultiDiGraph(startNodeId=contactFlow['StartAction'])
        # flow["graph"] = graph  # this is not serializable - maybe add it or a json version at the end..?
        flow["contactAttributes"] = {}
        flow["lambdaFunctions"] = {}
        flow["lexBots"] = {}
        # startNodeId = contactFlow['StartAction']

        # read the actions section
        actionsList = contactFlow[CONTACTFLOW_ACTIONS]
        # log.debug("actionsList:")
        # log.debug(json.dumps(actionsList, indent=2))

        ix = -1
        for actionDict in actionsList:
            ix = ix + 1
            # notice each node contains all the info from the original connect flow
            # temp - move to separate function
            t_type = actionDict["Type"]
            additional_data = {
                "label": actionDict["Type"]
            }
            if t_type == "TransferContactToQueue":
                additional_data["label"] = "{0}\n{1}".format(t_type, actionDict["Identifier"])


            if t_type == "TransferToFlow":
                # print(json.dumps(actionDict))
                contactFlowId = "Dynamic (TBD)"
                # handle hardcoded
                if "ContactFlowId" in actionDict["Parameters"]:
                    contactFlowId = actionDict["Parameters"]["ContactFlowId"] # is actually the ARN
                    contactFlowId = contactFlowId.split("/")[-1]
                    # print(contactFlowId)

                additional_data["label"] = "{0}\n{1}".format(t_type, contactFlowId)


            if t_type == "Compare":
                additional_data["label"] = "{0}\n{1}".format(t_type, actionDict["Parameters"]["ComparisonValue"])
                # update the contact attr metadata for the flow
                self.updateContactAttrUsage(actionDict["Parameters"]["ComparisonValue"], flow, "used")

            if t_type == "InvokeFlowModule":
                flowModuleName = actionDict["Parameters"]["FlowModuleId"] # set at least default
                # NOTE: real replacement should be done when exporting to another format - like PLT
                if flowModuleName in self.resourceIdNameMap:
                    flowModuleName = self.resourceIdNameMap[flowModuleName]
                additional_data["label"] = "{0}\n{1}".format(t_type, flowModuleName)
                # update the contact attr metadata for the flow
                # self.updateContactAttrUsage(actionDict["Parameters"]["ComparisonValue"], flow, "used")


            if t_type == "UpdateContactAttributes": # does not include system variables set
                tooltip = ""
                for key, value in actionDict["Parameters"]["Attributes"].items():
                    # create the tooltop
                    tooltip = '{0}{1} = {2}'.format(tooltip, key, value)
                    # update the contact attr metadata for the flow
                    self.updateContactAttrUsage(key, flow, "updated")
                additional_data["tooltip"] = "'{0}'".format(re.escape(tooltip))

            if t_type == "UpdateContactData":  # if System variables are set in update contact attrs block
                tooltip = ""
                for key, value in actionDict["Parameters"].items():
                    key = "System.{0}".format(key)
                    # create the tooltop
                    tooltip = '{0}{1} = {2}'.format(tooltip, key, value)
                    # update the contact attr metadata for the flow
                    self.updateContactAttrUsage(key, flow, "updated")
                additional_data["tooltip"] ="'{0}'".format(re.escape(tooltip))


            if t_type == "GetParticipantInput":
                # print(">>>>> actionDict: {0}")
                params = actionDict["Parameters"]
                # print(">>>>> Parameters: {0}".format(json.dumps(actionDict["Parameters"])))
                if "SSML" in params:
                    # print("+++ SSML: ", str(params["SSML"])).encode('unic')
                    additional_data["tooltip"] = "'{0}'".format(re.escape(params["SSML"]))
                if "Text" in params:
                    additional_data["tooltip"] = "'{0}'".format(re.escape(params["Text"]))

            if t_type == "MessageParticipant":
                params = actionDict["Parameters"]
                # print(">>>>> Parameters: {0}".format(json.dumps(actionDict["Parameters"])))
                if "SSML" in params:
                    additional_data["tooltip"] = "'{0}'".format(re.escape(params["SSML"]))
                if "Text" in params:
                    additional_data["tooltip"] = "'{0}'".format(re.escape(params["Text"]))

            if t_type == "InvokeLambdaFunction":
                params = actionDict["Parameters"]
                # print(json.dumps(params, indent=2))
                # update the label
                additional_data["label"] = "{0}\n{1}".format(t_type, params["LambdaFunctionARN"])

                tooltip = "{0} Timeout_ {1}".format(params["LambdaFunctionARN"], params["InvocationTimeLimitSeconds"])
                if "LambdaInvocationAttributes" in params:
                    # more lines so add new line
                    tooltip = tooltip + "\n{"
                    for key, value in params["LambdaInvocationAttributes"].items():
                        # print(key)
                        tooltip = "{0}{1}={2}\n".format(tooltip, key, value)
                    tooltip = tooltip + "}"
                    # example of setting additional values for PLT format.
                    # additional_data["fillcolor"]="blue"
                    # additional_data["style"]="filled"
                    # additional_data["URL"]="../../lambdas/somelambda1/index.html"                    
                additional_data["tooltip"] = tooltip
                # capture the lambda function usage
                self.updateLambdaFunctionUsage(params["LambdaFunctionARN"], flow)


            if t_type == "ConnectParticipantWithLexBot":
                params = actionDict["Parameters"]
                # print(json.dumps(params, indent=2))

                # TODO: Will need to handle dynamic params
                toolTip = ""
                # deal with non-dynamically set
                if "LexBot" in params:
                    lexParams = params["LexBot"]
                    compositeName = "{0}:{1}:{2}".format(lexParams["Region"], lexParams["Name"], lexParams["Alias"])
                    additional_data["label"] = "{0}\n{1}".format(t_type, compositeName)
                    additional_data["tooltip"] = compositeName
                    # capture the lambda function usage
                    self.updateLexBotUsage(compositeName, flow)


            # print("Additional Data: ", actionDict['Identifier'], " : ", additional_data)
            # print("Adding node: ", actionDict['Identifier'], "  :   ", actionDict, additional_data)
            # add the node (any object) as just the identifier, then 'data' is an attr as are the name value pairs in additional_data

            graph.add_node(actionDict['Identifier'], data=actionDict, **additional_data)
            # graph.add_node(actionDict['Identifier'], data=actionDict)


        # --- now generate the edges

        # indented from here
        # create set of all node types
        nodeTypesSet = set()

        # process the nodes
        edgesToAdd = []
        # print('=== Adding Edges ===')
        # print(graph.nodes.items())
        try:
            for node, nodeData in graph.nodes.items():

                nodeData = nodeData['data']  # reassign the data

                # add type to the set of all types
                nodeTypesSet.add(nodeData['Type'])

                # figure out if it's a end node
                connectNodeType = nodeData['Type']
                if connectNodeType in endNodeTypes:
                    endNodeIds.append(nodeData['Identifier'])

                # Generate the edges from the Connect Transition info
                transitions = nodeData['Transitions']
                if ('NextAction' in transitions) and (connectNodeType not in ['Compare', 'GetParticipantInput']):
                    edgesToAdd.append({
                        'type': 'default',
                        'identifier': nodeData['Identifier'],
                        'nextAction': transitions['NextAction']
                    })
                    graph.add_edge(nodeData['Identifier'],
                                transitions['NextAction'], type='Default', isError=False,
                                #    label='Default'
                                )

                if 'Errors' in transitions: 
                    for error in transitions['Errors']:
                        # errors - may want to be able to toggle various error conditions/defaults on/off
                        includeAllErrorTypes = True
                        if error['ErrorType'] in ['NoMatchingCondition'] or includeAllErrorTypes:
                            graph.add_edge(nodeData['Identifier'], error['NextAction'],
                                        type=error['ErrorType'], isError=True,
                                        label=error['ErrorType'])

                if 'Conditions' in transitions:
                    for condition in transitions['Conditions']:
                        label = "{0} {1}".format(condition["Condition"]["Operator"], condition["Condition"]["Operands"])
                        graph.add_edge(nodeData['Identifier'], condition['NextAction'],
                                    type='Condition',
                                    isError=False,
                                    label=label,
                                    parameters=nodeData['Parameters'] if 'Parameters' in nodeData else [],
                                    condition=condition['Condition'])

        except Exception as err:
            traceback.print_exc()
            print("!!! Error caught: {0}".format(err))
            raise

        flow["graphAsDot"] = Ghostwriter.get_raw_dot(graph)

        # === END: process the flow


    def updateContactAttrUsage(self, contactAttrName, flow, usage):
        # remove any $.Attributes
        contactAttrName = contactAttrName.replace("$.Attributes.", "")

        # START: process for the global usage dictionary
        modelAttrs = self.model["contactAttributes"]

        # create entry if it does not exist
        if contactAttrName not in modelAttrs.keys():
            modelAttrs[contactAttrName] = {
                "updatedInFlow": [],    # really wanted to use a set here to avoid checking duplicates later
                "usedInFlow": []        # really wanted to use a set here to avoid checking duplicates later
            }
        if usage == "used":
            if flow['Name'] not in modelAttrs[contactAttrName]["usedInFlow"]:
                modelAttrs[contactAttrName]["usedInFlow"].append(flow['Name'])
        if usage == "updated":
            if flow['Name'] not in modelAttrs[contactAttrName]["updatedInFlow"]:
                modelAttrs[contactAttrName]["updatedInFlow"].append(flow['Name'])


        # END: process global attr


        # process for the flow usage
        flowContactAttrs = flow["contactAttributes"]
        if contactAttrName not in flowContactAttrs.keys():
            # add it with defaults
            flowContactAttrs[contactAttrName] = {
                "contactAttrName": contactAttrName,
                "usedInFlow": False,
                "updatedInFlow": False
            }
        # set the usage based on what we see
        if usage == "used":
            flowContactAttrs[contactAttrName]["usedInFlow"] = True
        if usage == "updated":
            flowContactAttrs[contactAttrName]["updatedInFlow"] = True


    def updateLambdaFunctionUsage(self, functionName, flow):
        # remove any $.Attributes
        # contactAttrName = contactAttrName.replace("$.Attributes.", "")

        # START: process for the global usage dictionary
        modelAttrs = self.model["lambdaFunctions"]

        # create entry if it does not exist
        if functionName not in modelAttrs.keys():
            modelAttrs[functionName] = {
                "usedInFlow": []        # really wanted to use a set here to avoid checking duplicates later
            }
        if flow['Name'] not in modelAttrs[functionName]["usedInFlow"]:
            modelAttrs[functionName]["usedInFlow"].append(flow['Name'])
        # END: process global attr


        # process for the actual flow usage
        lambdaFunctions = flow["lambdaFunctions"]
        if functionName not in lambdaFunctions.keys():
            # add it with defaults
            lambdaFunctions[functionName] = {
                "functionName": functionName,
                "usedInFlow": True
            }
        

    def updateLexBotUsage(self, lexBotName, flow):
        # remove any $.Attributes
        # contactAttrName = contactAttrName.replace("$.Attributes.", "")

        # START: process for the global usage dictionary
        modelAttrs = self.model["lexBots"]

        # create entry if it does not exist
        if lexBotName not in modelAttrs.keys():
            modelAttrs[lexBotName] = {
                "usedInFlow": []        # really wanted to use a set here to avoid checking duplicates later
            }
        if flow['Name'] not in modelAttrs[lexBotName]["usedInFlow"]:
            modelAttrs[lexBotName]["usedInFlow"].append(flow['Name'])
        # END: process global attr


        # process for the actual flow usage
        lexBots = flow["lexBots"]
        if lexBotName not in lexBots.keys():
            # add it with defaults
            lexBots[lexBotName] = {
                "lexBotName": lexBotName,
                "usedInFlow": True
            }



    @staticmethod
    def get_raw_dot(graph):
        """Generates the DOT langauge version of the dependencies
        
        See https://graphviz.org/doc/info/lang.html for more info.

        :return: a DOT language string"""
        exported_graph = nx.nx_pydot.to_pydot(graph)
        raw_dot = exported_graph.to_string()
        return raw_dot




        # contactFlowName = flow[CONTACTFLOWINFO_NAME]


        # # print(contactFlowName)
        # # add a new node to the graph for the flow
        # self.graph.add_node(contactFlowName)

        # self.__process_flow_references(flow, "flow", "Metadata.ActionMetadata.*.contactFlow")
        # self.__process_flow_references(flow, "flow", "Metadata.ActionMetadata.*.ContactFlow")
        # self.__process_flow_references(flow, "module", "Metadata.ActionMetadata.*.contactFlowModuleName")

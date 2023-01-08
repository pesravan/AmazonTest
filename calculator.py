# © 2022 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.  
# This AWS Content is provided subject to the terms of the AWS Customer Agreement available at  
# http://aws.amazon.com/agreement or other written agreement between Customer and either
# Amazon Web Services, Inc. or Amazon Web Services EMEA SARL or both.

import json
import networkx as nx
import jmespath

CONTACTFLOWINFO_NAME = 'Name'
CONTACTFLOWINFO_CONTENT = 'Content'

class Calculator:
    """Calculates the contact flow dependecies to help with deployments"""

    def __init__(self):
        """Initializes the object
        """
        self.flows = {}
        self.graph = nx.DiGraph()

    def __process_flow_references(self, flow, type, jmespathstr):
        contactFlowName = flow[CONTACTFLOWINFO_NAME]
        contactFlowContent = json.loads(flow[CONTACTFLOWINFO_CONTENT])


        # find all the hardcoded contact flow references - differnt capitalizations used in JSON
        transferToEntriesArray = jmespath.search(jmespathstr,contactFlowContent)

        # print(json.dumps(transferToEntriesArray, indent=2))

        for transferToEntry in transferToEntriesArray:
            # create an edge between 2 nodes 
            if type == "module":
                self.graph.add_edge(contactFlowName, transferToEntry)
            else:
                self.graph.add_edge(contactFlowName, transferToEntry['text'])



    def process_flow(self, flow):
        """Processes a contact flow and determines the flows it is dependent on
        
        :param flow: contact flow json retrieved from an Amazon Connect instance via the API
        """
        # TODO: validate that it has the right structure

        # print(json.dumps(flow, indent=2))
        contactFlowName = flow[CONTACTFLOWINFO_NAME]


        # print(contactFlowName)
        # add a new node to the graph for the flow
        self.graph.add_node(contactFlowName)

        self.__process_flow_references(flow, "flow", "Metadata.ActionMetadata.*.contactFlow")
        self.__process_flow_references(flow, "flow", "Metadata.ActionMetadata.*.ContactFlow")
        self.__process_flow_references(flow, "module", "Metadata.ActionMetadata.*.contactFlowModuleName")

    def print_flows(self):
        """Print the contact flow data that has been processed
        """
        print(json.dumps(self.flows, indent=2))
    
    def get_dependencies(self):
        """Get the list of dependencies that has been calculated 
        
        :return: A list containing dictionary objects.  Each dictionary contains the "name" and "dependencies" array for the flow.

        """
        # create (ordered) list to store the returned info
        dependencies = []
        sortedGraph = reversed(list(nx.topological_sort(self.graph)))

        for nodeId in sortedGraph:
            dependsOn = []
            for edge in self.graph.out_edges([nodeId]):
                dependsOn.append(edge[1])

            dependencies.append({
                "name": nodeId,
                "dependsOn": dependsOn
                })
            # print("{0}: {1}".format(nodeId, dependsOn))

        return dependencies

    def flows_contain_cycles(self):
        """Determine if the flows contain cycles/loops in the dependecies.
        
        :return: Boolean identifying if there is a t least one cycle/loop.
        """
        cyclesList = list(nx.simple_cycles(self.graph))
        if len(cyclesList) > 0: return True
        return False

    def get_cycles_list(self):
        """Get a list of the cycles/loops
        
        :return: A List with item being a list of the flow names that make up a cycle.
        """
        return list(nx.simple_cycles(self.graph))

    def get_raw_dot(self):
        """Generates the DOT langauge version of the dependencies
        
        See https://graphviz.org/doc/info/lang.html for more info.

        :return: a DOT language string"""
        exported_graph = nx.nx_pydot.to_pydot(self.graph)
        raw_dot = exported_graph.to_string()
        return raw_dot

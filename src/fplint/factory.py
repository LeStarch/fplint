""" Factory Helper Methods to orchistrait creation of one model to rule them all """
import copy

from typing import Tuple, List

from fprime_ac.parsers.XmlPortsParser import XmlPortsParser
from fprime_ac.parsers.XmlSerializeParser import XmlSerializeParser
from fprime_ac.parsers.XmlComponentParser import XmlComponentParser
from fprime_ac.parsers.XmlTopologyParser import XmlTopologyParser


from fprime_ac.models.PortFactory import PortFactory
from fprime_ac.models.CompFactory import CompFactory
from fprime_ac.models.TopoFactory import TopoFactory

from fprime_ac.models.Port import Port
from fprime_ac.models.Component import Component
from fprime_ac.models.Topology import Topology

from fprime_ac.utils.buildroot import search_for_file

def merge_object_model(amalgam, traits):
    """ Merges two incompletly specified objects """
    assert type(amalgam) == type(traits), "Inconsistent type merge impossible"
    for attr in set(list(amalgam.__dict__.keys()) + list(traits.__dict__.keys())):
        trait_value = getattr(traits, attr, None)
        amalgam_value = getattr(amalgam, attr, None)
        # Make sure trait will not destroy existing trait
        if trait_value is None:
            continue
        # Recurse for ports
        elif attr == "_Component__port_obj_list":
            for port in amalgam._Component__port_obj_list:
                trait_port = traits.get_port_by_name(port.get_name(), port.get_source_num())
                if trait_port is None:
                    continue
                merge_object_model(port, trait_port)
            new_ports = [port for port in traits._Component__port_obj_list if amalgam.get_port_by_name(port.get_name(), port.get_source_num()) is None]
            for new_port in new_ports:
                amalgam._Component__port_obj_list.append(new_port)
            continue
        elif attr.endswith("__xml_filename"):
            pass
        # Code uses different names
        elif isinstance(amalgam_value, str) and isinstance(trait_value, str) and amalgam_value.lower() == trait_value.lower():
            pass
        elif amalgam_value is None or amalgam_value == "" or (isinstance(amalgam_value, (list, tuple)) and len(amalgam_value) == 0) or not amalgam_value:
            pass
        elif attr == "_Port__ptype" and amalgam_value.endswith(trait_value):
            continue
        elif attr == "_Component__modeler":
            continue
        elif amalgam_value is not None and trait_value != amalgam_value:
            raise InconsistencyException("{} has inconsistent definitions ".format(amalgam.get_name()))
        setattr(amalgam, attr, trait_value)
    return amalgam

def mega_port_loader(port_xml: str) -> Tuple[Port, XmlPortsParser]:
    """ Loads a port from an XML filename"""
    port_file = search_for_file("Port", port_xml)
    parsed_port_xml = XmlPortsParser(port_file)
    port = PortFactory.getInstance().create(parsed_port_xml)
    return port, parsed_port_xml

def mega_ser_loader(ser_xml: str) -> XmlSerializeParser:
    """ Loads the serializable """
    serializable_file = search_for_file("Serializable", ser_xml)
    xml_parser_obj = XmlSerializeParser(serializable_file)
    # Telemetry/Params can only use generated serializable types
    # check to make sure that the serializables don't have things that channels and parameters can't have
    # can't have external non-xml members
    if len(xml_parser_obj.get_include_header_files()):
        raise Exception("ERROR: Component include serializables cannot use user-defined types. file: {}"
                        .format(serializable_file))
    return xml_parser_obj


def mega_component_loader(comp_xml: str) -> Component:
    """ This is the mega system loader from topology and down """
    comp_file = search_for_file("Component", comp_xml)
    parsed_comp_xml = XmlComponentParser(comp_file)

    port_pairs = [mega_port_loader(port_file) for port_file in set(parsed_comp_xml.get_port_type_files())]
    ser_xmls = [mega_ser_loader(ser_file) for ser_file in parsed_comp_xml.get_serializable_type_files()]
    port_objs = {pair[0].get_type(): pair[0] for pair in port_pairs}
    port_objs["Serial"] = Port(None, "Serial", None)

    comp = CompFactory.getInstance().create(parsed_comp_xml, [pair[1] for pair in port_pairs], ser_xmls)

    # Due to an inconsistent model, we have to rewrite the loaded model here
    comp._Component__kind2 = comp._Component__kind
    comp._Component__kind = comp._Component__name
    comp._Component__name = None

    # Due to an inconsistency, port models only load one "port" and not 0-max num-1 ports of each name
    appendables = []
    for port in comp.get_ports():
        # Clone and enumerate ports
        port.set_source_num(0)
        for i in range(1, int(port.get_max_number())):
            new_port = copy.deepcopy(port)
            new_port.set_source_num(i)
            appendables.append(new_port)
    comp.get_ports().extend(appendables)

    for port in comp.get_ports():
        port_spec = port_objs[port.get_type()]
        try:
            merge_object_model(port, port_spec)
        except InconsistencyException as inc:
            raise InconsistencyException("Inconsistency detected between Component and Port specification: {}.{}. {}"
                                         .format(comp.get_kind(), comp.get_name(), inc)) from inc
    return comp

def fix_target_ports(topology: Topology, xml_topology: XmlTopologyParser):
    """ """
    for component in topology.get_comp_list():
        port_obj_list = []
        for connection in xml_topology.get_connections():
            if component.get_name() == connection.get_target()[0]:
                port = Port(
                    connection.get_target()[1],
                    connection.get_target()[2],
                    None,
                    None,
                    comment=connection.get_comment(),
                    xml_filename=xml_topology.get_xml_filename,
                )
                port.set_source_num(connection.get_target()[3])
                port.set_target_comp(connection.get_source()[0])
                port.set_target_port(connection.get_source()[1])
                port.set_target_type(connection.get_source()[2])
                port.set_target_num(connection.get_source()[3])
                port.set_direction("input")
                port.set_target_direction("output")
                component.get_ports().append(port)

def mega_topology_loader(topology_xml: str) -> Topology:
    """ Load the topology from XML """
    top_factory = TopoFactory.getInstance()
    parsed_topology = XmlTopologyParser(str(topology_xml))
    imported_comps = [mega_component_loader(comp_xml) for comp_xml in set(parsed_topology.get_component_includes())]
    comp_objs = {comp.get_kind(): comp for comp in imported_comps}
    model = top_factory.create(parsed_topology)
    fix_target_ports(model, parsed_topology)
    for comp in model.get_comp_list():
        comp_spec = comp_objs[comp.get_kind()]
        try:
            merge_object_model(comp, comp_spec)
        except InconsistencyException as inc:
            raise InconsistencyException("Inconsistency detected in Topology vs XML Specification: {}.{}. {}"
                                         .format(comp.get_kind(), comp.get_name(), inc)) from inc
    return model

class InconsistencyException(Exception):
    pass
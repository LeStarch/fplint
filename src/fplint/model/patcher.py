""" Code required to load and patch the native fprime autocoder models

The fprime autocoder provides a models package that represents fprime as a graph of interconnected ports attached to a
set of component instances. However, this model is constructed and used in two divergent ways. On focuses on the
component instantiation, and the other on the component model.  Proper validation requires checking on both sides of
this divide. Thus, this code attempts to merge the two models into a useful final result.

Clarifications on the resulting model:

1. Port arrays are expanded into unique ports portName.#
2. Port target properties now refer to the other side of the connection, regardless if a port is an input or output,
   source or target. Similarly, source properties refer to the current port.
3. Unconnected ports have target properties of None
4. Input ports instantiations are included
5. Component "name" now refers to the instance name, "kind" refers to the component type, and "kind2" refers to
   active/passive

This file also handles including of the fprime_ac code on the python path to ensure access to the code.  Lastly, it
sets up the build root shim such that users need not set BUILD_ROOT variables.
"""
import copy
import os
from typing import Tuple
from pathlib import Path
import sys


from fprime.fbuild.settings import IniSettings, FprimeLocationUnknownException, FprimeSettingsException

# Weeping sadness: fprime_ac is not available as a package, so setting must be loaded globally and python path adjusted
#                  before anu fprime_ac modules are loaded. The BUILD_ROOT options then need to be patched such that the
#                  fprime_ac modules work as expected.
try:
    __settings = IniSettings.load(None, cwd=Path.cwd())
    ac_code_root = Path(__settings.get("framework_path")) / "Autocoders" / "Python" / "src"
    sys.path.append(str(ac_code_root))
except (FprimeLocationUnknownException, FprimeSettingsException):
    print("[WARNING] Unable to load true fprime autocoder models. Will use vendor fallback", file=sys.stderr)
    __vendor_fallback = Path(__file__).parent.parent.parent.parent / "vendor" / "fprime" / "Autocoders" / "Python" / "src"
    sys.path.append(__vendor_fallback)

#### Should all be available from fprime or vendor fallback ####
from fprime_ac.utils.buildroot import get_build_roots, set_build_roots, search_for_file
from fprime_ac.models.Topology import Topology
from fprime_ac.models.Component import Component
from fprime_ac.models.Port import Port
# Loading and model imports
from fprime_ac.models.TopoFactory import TopoFactory
from fprime_ac.models.CompFactory import CompFactory
from fprime_ac.models.PortFactory import PortFactory
from fprime_ac.parsers.XmlTopologyParser import XmlTopologyParser
from fprime_ac.parsers.XmlComponentParser import XmlComponentParser
from fprime_ac.parsers.XmlPortsParser import XmlPortsParser
from fprime_ac.parsers.XmlSerializeParser import XmlSerializeParser


def load_patched_topology(topology_xml: Path, settings_dir: Path = None) -> Topology:
    """ Loads a patched model of the topology

    Loads a topology and attempts to correlate it across the various specification files. It is returned as a "Topology"
    object, which can be validated.

    Args:
        topology_xml: topology XML path to load. XML validation should occur first.
        settings_dir: (optional) directory with settings.ini. Default: location of settings.ini w.r.t toplogy_xml

    Returns:
        topology module
    """
    settings_dir = topology_xml.parent.parent if settings_dir is None else settings_dir
    settings = IniSettings.load(None, cwd=settings_dir)

    # Any patching for the AC models will be undone afterwards
    build_roots_old = get_build_roots()
    ac_constants_old = os.environ.get("FPRIME_AC_CONSTANTS_FILE", None)
    try:
        # Base locations as dictated by the settings file
        base_locations = [settings.get("framework_path"), settings.get("project_root", None)]
        base_locations.extend(settings.get("library_locations", []))

        # Setup build roots for using the autocoder modules
        set_build_roots(":".join([str(location) for location in base_locations if location is not None]))
        ac_consts = Path(settings.get("ac_constants", Path(settings.get("framework_path")) / "config" / "AcConstants.ini"))
        if ac_consts and ac_consts.exists():
            os.environ["FPRIME_AC_CONSTANTS_FILE"] = str(ac_consts)
        # Now that all the environment patching is finished, loads of the toplogy model should run smoothly
        try:
            return __topology_loader(topology_xml)
        except InconsistencyException as inc:
            raise # Pass through if already inconsistency exception
        except Exception as exc:
            # Remap non-InconsistencyException exceptions
            raise InconsistencyException("Error when loading model: {}".format(exc)) from exc
    # Clean-up the system state after our loading
    finally:
        set_build_roots(":".join(build_roots_old))
        if ac_constants_old is not None:
            os.environ["FPRIME_AC_CONSTANTS_FILE"] = ac_constants_old


def __topology_loader(topology_xml: Path) -> Topology:
    """ Loads the topology XML into an autocoder model """
    top_factory = TopoFactory.getInstance()
    parsed_topology = XmlTopologyParser(str(topology_xml))
    imported_comps = [__component_loader(comp_xml) for comp_xml in set(parsed_topology.get_component_includes())]
    comp_objs = {comp.get_kind(): comp for comp in imported_comps}
    model = top_factory.create(parsed_topology)
    # Inconsistency #4
    __patch_target_ports(model, parsed_topology)
    for comp in model.get_comp_list():
        comp_spec = comp_objs[comp.get_kind()]
        try:
            __merge_object_model(comp, comp_spec)
        except InconsistencyException as inc:
            raise InconsistencyException("Inconsistency detected in Topology vs XML Specification: {}.{}. {}"
                                         .format(comp.get_kind(), comp.get_name(), inc)) from inc
    return model


def __component_loader(comp_xml: Path) -> Component:
    """ This is the mega system loader from topology and down """
    comp_file = search_for_file("Component", str(comp_xml))
    parsed_comp_xml = XmlComponentParser(comp_file)

    port_pairs = [__port_loader(port_file) for port_file in set(parsed_comp_xml.get_port_type_files())]
    ser_xmls = [__ser_loader(ser_file) for ser_file in parsed_comp_xml.get_serializable_type_files()]
    port_objs = {pair[0].get_type(): pair[0] for pair in port_pairs}
    port_objs["Serial"] = Port(None, "Serial", None)

    comp = CompFactory.getInstance().create(parsed_comp_xml, [pair[1] for pair in port_pairs], ser_xmls)

    # Inconsistency #5: Due to an inconsistent model, we have to rewrite the loaded component specification fields here
    comp._Component__kind2 = comp._Component__kind
    comp._Component__kind = comp._Component__name
    comp._Component__name = None

    # Inconsistency #1: component models only load one "port" and not 0-(max num - 1) ports of each type
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
            __merge_object_model(port, port_spec)
        except InconsistencyException as inc:
            raise InconsistencyException("Inconsistency detected between Component and Port specification: {}.{}. {}"
                                         .format(comp.get_kind(), comp.get_name(), inc)) from inc
    return comp


def __merge_object_model(amalgam, traits):
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
                trait_port = get_port_by_name(traits, port.get_name(), port.get_source_num())
                if trait_port is None:
                    continue
                __merge_object_model(port, trait_port)
            new_ports = [port for port in traits._Component__port_obj_list if get_port_by_name(amalgam, port.get_name(), port.get_source_num()) is None]
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


def __port_loader(port_xml: str) -> Tuple[Port, XmlPortsParser]:
    """ Loads a port from an XML filename"""
    port_file = search_for_file("Port", port_xml)
    parsed_port_xml = XmlPortsParser(port_file)
    port = PortFactory.getInstance().create(parsed_port_xml)
    return port, parsed_port_xml


def __ser_loader(ser_xml: str) -> XmlSerializeParser:
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


def __patch_target_ports(topology: Topology, xml_topology: XmlTopologyParser):
    """ Inconsistency #4: Include input (target) ports in the instance model """
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


def get_port_by_name(component: Component, name: str, index) -> Port:
    """ Returns the component model of a component with given name. """
    ports = [port for port in component.get_ports() if port.get_name() == name]
    if not ports:
        return None
    ports_of_index = [port for port in ports if port.get_source_num() == index]
    if not ports_of_index:
        return None
    return ports_of_index[0]


def get_comp_by_name(model: Topology, name: str) -> Component:
    """ Returns the component model of a component with given name. """
    comps = [comp for comp in model.get_comp_list() if comp.get_name() == name]
    if not comps:
        return None
    elif len(comps) > 1:
        raise InconsistencyException("Multiple components with name {} defined".format(name))
    return comps[0]


class InconsistencyException(Exception):
    """ Exception pertaining to the model being in a verifiable state """
    pass
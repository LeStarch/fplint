""" Hub checker performing cross-topology linting for a better future

Hub check works in mysterious ways.  First off, it does basic port-in port out consistency checks. This makes sure that
the the ports going in and out of a hub pair are parallel. Failure to do so causes systematic failure of the Hub
pattern. Next, it will attempt to massage the model such that is virtualizes away the hub. Then it will attempt to rerun
other checks (like command_ports) to check them --across the hub--.  Will it work? Perhaps.
"""
import copy
from pathlib import Path
from typing import List, Dict


from fplint.model.patcher import load_patched_topology
from fplint.model.patcher import InconsistencyException, Component, Port, Topology, get_comp_by_name, get_port_by_name

from fplint.check import CheckBase, CheckSeverity, CheckResult

from .command_ports import CommandPorts
from .connected import PortConnections
from .collisions import PortCollision

class HubResultDelegator(CheckResult):
    """ A check result that deletgates to another, with some extra remappinf"""
    def __init__(self, delegate: CheckResult):
        self.delegate = delegate

    """ Remaps (possibly filtered) check into the hub namespace such that they can be independently filtered """
    def add_problem(self, ident: str, *args, **kwargs):
        """ Remaps problems for hub namespace """
        self.delegate.add_problem("hub-"+ident, *args, **kwargs)

class HubLinter(CheckBase):
    """ Hub linter """
    PORT_PAIRS = {"portIn": "portOut", "portOut": "portIn", "buffersIn": "buffersOut", "buffersOut": "buffersIn"}
    DELGATED_CHECKS = [PortCollision, CommandPorts]

    @staticmethod
    def get_extra_arguments():
        """ Returns a list of extra arguments needed by this lint checker """
        return {
            "hub-remote-topology": {"type": str, "help": "Topology XML of the remote side of the hub pair"},
            "hub-local-hub-name":  {"type": str, "help": "Name of hub component in this topology"},
            "hub-remote-hub-name": {"type": str, "help": "Name of hub component in the remote topology"}
        }

    @classmethod
    def get_identifiers(cls) -> Dict[str, CheckSeverity]:
        """ Returns identifiers produced here."""
        notifiers = {}
        for delegate in cls.DELGATED_CHECKS:
            notifiers.update({"hub-{}".format(key): value for key, value in delegate.get_identifiers().items()})
        notifiers.update({
            "hub-colliding-ids": CheckSeverity.ERROR,
            "hub-ports-unused": CheckSeverity.WARNING,
            "hub-ports-not-connected": CheckSeverity.ERROR,
            "hub-ports-not-parallel": CheckSeverity.ERROR,
            "hub-port-directions-not-parallel": CheckSeverity.ERROR,
            "hub-unused-ports-not-parallel": CheckSeverity.ERROR
        })
        return notifiers

    @staticmethod
    def get_component_port(model: Topology, port: Port):
        """ Get the component ports """
        component = get_comp_by_name(model, port.get_target_comp())
        if component is None:
            return None
        return get_port_by_name(component, port.get_target_port(), port.get_target_num())

    @classmethod
    def get_sorted_hub_ports(cls, model: Topology, hub_name: str):
        """ Gets the ports for the hub in index-sorted order """
        ports_dict = {}
        hub_object = get_comp_by_name(model, hub_name)
        for port_name in cls.PORT_PAIRS.keys():
            port_zero = get_port_by_name(hub_object, port_name, 0)
            hub_ports = [get_port_by_name(hub_object, port_name, num) for num in range(0, int(port_zero.get_max_number()))]
            cmp_ports = [cls.get_component_port(model, port) for port in hub_ports]
            ports_dict[port_name] = list(zip(hub_ports, cmp_ports))
        return ports_dict


    def run(self, result: CheckResult, model: Topology, extras: List[str]) -> CheckResult:
        """ Run it """
        topology_path, local_hub_name, remote_hub_name = extras[0], extras[1], extras[2]
        remote_model = load_patched_topology(Path(topology_path))
        local_model = copy.deepcopy(model) # we will do terrible things to this topology

        # Args validation
        if get_comp_by_name(local_model, local_hub_name) is None:
            raise Exception("Could not find component '{}' in local topology".format(local_hub_name))
        elif get_comp_by_name(remote_model, remote_hub_name) is None:
            raise Exception("Could not find component '{}' in remote topology".format(remote_hub_name))

        # Get comparable sets
        local_ports_dict = self.get_sorted_hub_ports(local_model, local_hub_name)
        remote_ports_dict = self.get_sorted_hub_ports(remote_model, remote_hub_name)


        for port_key_local, port_key_remote in self.PORT_PAIRS.items():
            local_port_pairs = local_ports_dict.get(port_key_local)
            remote_port_pairs = remote_ports_dict.get(port_key_remote)
            combined_tmp = zip(local_port_pairs, remote_port_pairs)
            sequence = [(pair[0][0], pair[0][1], pair[1][0], pair[1][1]) for pair in combined_tmp]

            for local_hub_port, local_comp_port, remote_hub_port, remote_comp_port in sequence:
                # Checks that hub ports align correctly based on index
                if local_hub_port.get_source_num() != remote_hub_port.get_source_num():
                    result.add_problem("hub-unused-ports-not-parallel",
                                       "and {} should have aligning indices"
                                       .format(remote_model, remote_hub_name, remote_hub_port),
                                       local_model, local_hub_name, local_hub_port)
                # Warn if the hub ports are disconnected on both ends
                elif local_comp_port is None and remote_comp_port is None:
                    result.add_problem("hub-ports-unused",
                                       "and {} are both disconnected"
                                       .format(CheckBase.get_standard_identifier(remote_model, remote_hub_name, remote_hub_port)),
                                       local_model, local_hub_name, local_hub_port)
                # If a local port is connected but the remote hub port is not connected
                elif local_comp_port is not None and remote_comp_port is None:
                    result.add_problem("hub-ports-not-connected",
                                       "is connected to {} but remote {} is not connected"
                                       .format(CheckBase.get_standard_identifier(local_model, local_hub_name, local_hub_port),
                                               CheckBase.get_standard_identifier(remote_model, remote_hub_name, remote_hub_port)),
                                       local_model, local_hub_port.get_target_comp(), local_comp_port)
                elif local_comp_port is None and remote_comp_port is not None:
                    result.add_problem("hub-ports-not-connected",
                                       "is connected to {} but local {} is not connected"
                                       .format(CheckBase.get_standard_identifier(remote_model, remote_hub_name, remote_hub_port),
                                               CheckBase.get_standard_identifier(local_model, local_hub_name, local_hub_port)),
                                       remote_model, remote_hub_port.get_target_comp(), remote_comp_port)
                elif local_comp_port.get_type() != remote_comp_port.get_type():
                    result.add_problem("hub-ports-not-parallel",
                                       "of type {} at hub port {} is connected to {} of incompatible type {} at hub port {}"
                                       .format(local_comp_port.get_type(), CheckBase.get_standard_identifier(local_model, local_hub_name, local_hub_port),
                                               CheckBase.get_standard_identifier(remote_model, remote_hub_port.get_target_comp(), remote_comp_port), remote_comp_port.get_type(),
                                               CheckBase.get_standard_identifier(remote_model, remote_hub_name, remote_hub_port)),
                                       local_model, local_hub_port.get_target_comp(), local_comp_port)
                elif local_hub_port.get_direction() == remote_hub_port.get_direction():
                    result.add_problem("hub-port-directions-not-parallel",
                                       "of direction {} parallel to {} of incompatible direction {}"
                                       .format(local_hub_port.get_direction(),
                                               CheckBase.get_standard_identifier(remote_model, remote_hub_name, remote_hub_port),
                                               remote_comp_port.get_direction()),
                                       local_model, local_hub_name, local_hub_port)
                elif local_comp_port.get_direction() == remote_comp_port.get_direction():
                    result.add_problem("hub-port-directions-not-parallel",
                                       "of direction {} at hub port {} is connected to {} of incompatible direction {} at hub port {}"
                                       .format(local_comp_port.get_direction(), CheckBase.get_standard_identifier(local_model, local_hub_name, local_hub_port),
                                               CheckBase.get_standard_identifier(remote_model, remote_hub_port.get_target_comp(), remote_comp_port), remote_comp_port.get_direction(),
                                               CheckBase.get_standard_identifier(remote_model, remote_hub_name, remote_hub_port)),
                                       local_model, local_hub_port.get_target_comp(), local_comp_port)

        # Combine the topologies for cross-system checks
        local_model._Topology__name = "--COMBINED--"
        local_model.get_comp_list().extend(remote_model.get_comp_list())
        for port_key_local, port_key_remote in self.PORT_PAIRS.items():
            local_port_pairs = local_ports_dict.get(port_key_local)
            remote_port_pairs = remote_ports_dict.get(port_key_remote)
            combined_tmp = zip(local_port_pairs, remote_port_pairs)
            sequence = [(pair[0][0], pair[0][1], pair[1][0], pair[1][1]) for pair in combined_tmp]

            for local_hub_port, local_comp_port, remote_hub_port, remote_comp_port in sequence:
                # Local strung to remote
                if local_comp_port is not None:
                    local_comp_port.set_target_direction(remote_hub_port.get_target_direction())
                    local_comp_port.set_target_num(remote_hub_port.get_target_num())
                    local_comp_port.set_target_type(remote_hub_port.get_target_type())
                    local_comp_port.set_target_comp(remote_hub_port.get_target_comp())
                    local_comp_port.set_target_port(remote_hub_port.get_target_port())
                    # Clear hub ports
                    remote_hub_port.set_target_direction(None)
                    remote_hub_port.set_target_num(None)
                    remote_hub_port.set_target_type(None)
                    remote_hub_port.set_target_comp(None)
                    remote_hub_port.set_target_port(None)

                # Remote strung to remote
                if remote_comp_port is not None:
                    remote_comp_port.set_target_direction(local_hub_port.get_target_direction())
                    remote_comp_port.set_target_num(local_hub_port.get_target_num())
                    remote_comp_port.set_target_type(local_hub_port.get_target_type())
                    remote_comp_port.set_target_comp(local_hub_port.get_target_comp())
                    remote_comp_port.set_target_port(local_hub_port.get_target_port())
                    # Clear hub ports
                    local_hub_port.set_target_direction(None)
                    local_hub_port.set_target_num(None)
                    local_hub_port.set_target_type(None)
                    local_hub_port.set_target_comp(None)
                    local_hub_port.set_target_port(None)

        for checker in self.DELGATED_CHECKS:
            checker().run(HubResultDelegator(result), local_model, extras)
        return result


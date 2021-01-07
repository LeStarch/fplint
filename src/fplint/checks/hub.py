""" Hub checker performing cross-topology linting for a better future

Hub check works in mysterious ways.  First off, it does basic port-in port out consistency checks. This makes sure that
the the ports going in and out of a hub pair are parallel. Failure to do so causes systematic failure of the Hub
pattern. Next, it will attempt to massage the model such that is virtualizes away the hub. Then it will attempt to rerun
other checks (like command_ports) to check them --across the hub--.  Will it work? Perhaps.
"""
import os
from pathlib import Path
from typing import List, Dict

from fprime.fbuild.settings import IniSettings

from fprime_ac.models.Port import Port
from fprime_ac.models.Topology import Topology

from fplint.load import load_model

from .check import BaseCheck, CheckSeverity, CheckResult
from .command_ports import CommandPorts


class HubResultDelegator(CheckResult):
    """ Remaps (possibly filtered) check into the hub namespace such that they can be independently filtered """
    def add_problem(self, ident: str, *args, **kwargs):
        """ Remaps problems for hub namespace """
        super().add_problem("hub-", *args, **kwargs)

class HubLinter(BaseCheck):
    """ Hub linter """
    PORT_PAIRS = {"portIn": "portOut", "portOut": "portIn", "buffersIn": "buffersOut", "buffersOut": "buffersIn"}

    @staticmethod
    def load_with_remote_settings(topology):
        """ """
        settings_wd = topology.parent.parent
        settings = IniSettings.load(None, cwd=settings_wd)
        ac_consts = settings.get("ac_constants", None)
        if ac_consts and (settings_wd / ac_consts).exists():
            os.environ["FPRIME_AC_CONSTANTS_FILE"] = str(settings_wd /ac_consts)
        return load_model(topology)

    @staticmethod
    def get_extra_arguments():
        """ Returns a list of extra arguments needed by this lint checker """
        return {
            "hub-remote-topology": {"type": str, "help": "Topology XML of the remote side of the hub pair"},
            "hub-local-hub-name":  {"type": str, "help": "Name of hub component in this topology"},
            "hub-remote-hub-name": {"type": str, "help": "Name of hub component in the remote topology"}
        }

    @classmethod
    def get_identifiers(self) -> Dict[str, CheckSeverity]:
        """ Returns identifiers produced here."""
        return {
            "hub-ports-not-parallel": CheckSeverity.ERROR,
            "hub-port-directions-not-parallel": CheckSeverity.ERROR,
            "hub-unused-ports-not-parallel": CheckSeverity.ERROR
        }

    @staticmethod
    def get_component_port(model: Topology, port: Port):
        """ Get the component ports """
        component = model.get_comp_by_name(port.get_target_comp())
        if component is None:
            return None
        return component.get_port_by_name(port.get_target_port(), port.get_target_num())

    @classmethod
    def get_sorted_hub_ports(cls, model: Topology, hub_name: str):
        """ Gets the ports for the hub in index-sorted order """
        ports_dict = {}
        hub_object = model.get_comp_by_name(hub_name)
        for port_name in cls.PORT_PAIRS.keys():
            port_zero = hub_object.get_port_by_name(port_name, 0)
            hub_ports = [hub_object.get_port_by_name(port_name, num) for num in range(0, int(port_zero.get_max_number()))]
            cmp_ports = [cls.get_component_port(model, port) for port in hub_ports]
            ports_dict[port_name] = list(zip(hub_ports, cmp_ports))
        return ports_dict

    def run(self, result: CheckResult, model: Topology, extras: List[str]) -> CheckResult:
        """ Run it """
        remote_model_path = Path(extras[0])
        remote_model = self.load_with_remote_settings(remote_model_path)
        local_model = model
        # Args validation
        if local_model.get_comp_by_name(extras[1]) is None:
            raise Exception("Could not find component '{}' in local topology".format(extras[1]))
        elif remote_model.get_comp_by_name(extras[2]) is None:
            raise Exception("Could not find component '{}' in remote topology".format(extras[2]))

        # Get comparable sets
        local_ports_dict = self.get_sorted_hub_ports(local_model, extras[1])
        remote_ports_dict = self.get_sorted_hub_ports(remote_model, extras[2])

        for port_key_local, port_key_remote in self.PORT_PAIRS.items():
            local_hub_ports, local_comp_ports = local_ports_dict.get(port_key_local)
            remote_hub_ports, remote_comp_ports
            mega_zip = zip(*, *remote_ports_dict.get(port_key_remote))

            for local_hub_port, local_comp_port, remote_hub_port, remote_comp_port in mega_zip:
                # Check we don't have any holes
                if local_hub_port.get_source_num() != remote_hub_port.get_source_num():
                    result.add_problem("hub-unused-ports-not-parallel",
                                       "aligns with remote hub port at index {}"
                                       .format(remote_hub_port.get_source_num()), model, extras[1], local_hub_port)
                elif local_comp_port.get_type() != remote_comp_port.get_type():
                    result.add_problem("hub-ports-not-parallel",
                                       "aligns with incompatible type {} at hub port at index {}"
                                       .format(remote_comp_port.get_type(), remote_hub_port.get_source_num()),
                                       model, extras[1], local_hub_port)
                elif local_comp_port.get_direction() != remote_comp_port.get_direction():
                    result.add_problem("hub-port-directions-not-parallel",
                                       "aligns with incompatible direction {} at hub port at index {}"
                                       .format(remote_comp_port.get_direction(), remote_hub_port.get_source_num()),
                                       model, extras[1], local_hub_port)
        # TODO: rework model here

        return result





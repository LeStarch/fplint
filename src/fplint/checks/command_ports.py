from typing import Dict, List


from fprime_ac.models.Topology import Topology
from .check import BaseCheck, CheckSeverity, CheckResult


class CommandPorts(BaseCheck):
    """ A check that all ports are connected """
    CMD_TYPES = {"CmdReg": "output", "Cmd": "input", "CmdResponse": "output"}

    def __init__(self):
        self.component_mappings = {}

    @classmethod
    def get_identifiers(self) -> Dict[str, CheckSeverity]:
        """ Returns identifiers produced here."""
        return {
            "port-not-connected": CheckSeverity.WARNING,
            "command-ports-not-parallel": CheckSeverity.ERROR,
            "invalid-target-port-in-connection": CheckSeverity.ERROR
        }

    def run(self, result: CheckResult, model: Topology, extras: List[str]) -> CheckResult:
        """ Run the check """
        for component in model.get_comp_list():
            self.component_mappings[component.get_name()] = {key: None for key in self.CMD_TYPES.keys()}
            self.component_mappings[component.get_name()]["component"] = component
            for port in component.get_ports():
                port_type = port.get_type()
                port_dir = port.get_direction()
                port_target_number = port.get_target_num()
                port_target_comp = port.get_target_comp()
                port_target_port = port.get_target_port()
                port_target_type = port.get_target_type()

                # Only a check for connected ouput ports
                if port_type not in self.CMD_TYPES or port_dir.lower() != self.CMD_TYPES[port_type]:
                    continue
                if port_target_comp is None or port_target_port is None:
                    result.add_problem("port-not-connected", "command port not connected",
                                       model, component, port)
                    continue
                if port_target_type != "Serial" and port_target_type != port_type:
                    result.add_problem("invalid-target-port-in-connection", "command port connected to invalid type",
                                       model, component, port)
                    continue
                target_comp_obj = model.get_comp_by_name(port_target_comp)
                target_port_obj = target_comp_obj.get_port_by_name(port_target_port, port.get_target_num())
                self.component_mappings[component.get_name()][port_type] = target_port_obj
        for _, values in self.component_mappings.items():
            component = values["component"]
            reg = values["CmdReg"]
            cmd = values["Cmd"]
            rsp = values["CmdResponse"]

            # Get numbers
            reg = "n/a" if reg is None else reg.get_source_num()
            cmd = "n/a" if cmd is None else cmd.get_source_num()
            rsp = "n/a" if rsp is None else rsp.get_source_num()

            if reg == "n/a" and cmd == "n/a" and rsp == "n/a" and not component.get_commands():
                continue

            # Detect non-parellelism
            if reg != cmd or rsp != 0:
                result.add_problem("command-ports-not-parallel",
                                   "has non-parallel command ports: {},{},{}".format(reg, cmd, rsp), model, component)
        return result

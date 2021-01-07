from typing import Dict, List


from fprime_ac.models.Topology import Topology
from fprime_ac.models.exceptions import InvalidModel

from .check import BaseCheck, CheckSeverity, CheckResult


class PortConnections(BaseCheck):
    """ A check that all ports are connected """

    @classmethod
    def get_identifiers(self) -> Dict[str, CheckSeverity]:
        """ Returns identifiers produced here."""
        return {
            "port-not-connected": CheckSeverity.WARNING,
            "invalid-target-component-in-connection": CheckSeverity.ERROR,
            "invalid-target-port-in-connection": CheckSeverity.ERROR,
            "invalid-model-specification": CheckSeverity.ERROR,
            "conflicting-port-types-in-connection": CheckSeverity.ERROR,
            "conflicting-port-directions-in-connection": CheckSeverity.ERROR
        }

    def run(self, result: CheckResult, model: Topology, extras: List[str]) -> CheckResult:
        """ Run the check """
        for component in model.get_comp_list():
            for port in component.get_ports():
                # Get target component name
                if port.get_target_comp() is None or port.get_target_comp() == "":
                    result.add_problem("port-not-connected", "is not connected", model, component, port)
                    continue
                try:
                    target_comp = model.get_comp_by_name(port.get_target_comp())
                    if target_comp is None:
                        result.add_problem("invalid-target-component-in-connection",
                                           "connected to non-existent component {}".format(port.get_target_comp()),
                                           model, component, port)
                        continue
                    target_port = target_comp.get_port_by_name(port.get_target_port(), port.get_target_num())
                    if target_port is None:
                        result.add_problem("invalid-target-port-in-connection",
                                           "connected to non-existent port {}.{}:{}".format(target_comp.get_name(),
                                                                                            port.get_target_port(),
                                                                                            port.get_target_num()),
                                           model, component, port)
                        continue
                    if target_port.get_max_number() is None or int(target_port.get_max_number()) <= port.get_target_num():
                        result.add_problem("invalid-target-port-in-connection",
                                           "connected to non-existent port {}.{}:{}. Note: increase configured limits"
                                           .format(target_comp.get_name(), port.get_target_port(),
                                                   port.get_target_num()),
                                           model, component, port)
                        continue
                except InvalidModel as exc:
                    result.add_problem("invalid-model-specification", str(exc))
                    continue

                if not (port.get_type() == "Serial" or target_port.get_type() == "Serial" or port.get_type() == target_port.get_type()):
                    result.add_problem("conflicting-port-types-in-connection", "is connected to port {} of wrong type {}"
                                     .format(BaseCheck.get_standard_identifier(model, target_comp, target_port),
                                             target_port.get_type()), model, component, port)
                elif port.get_direction() == target_port.get_direction():
                    result.add_problem("conflicting-port-directions-in-connection",
                                       "is connected to  port {} of conflicting direction {}".format(
                                             BaseCheck.get_standard_identifier(model, target_comp, target_port),
                                             target_port.get_direction()), model, component, port)
        return result

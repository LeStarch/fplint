from typing import Dict, List


from fprime_ac.models.Topology import Topology
from fprime_ac.models.exceptions import InvalidModel

from .check import BaseCheck, CheckSeverity, CheckResult


class PortCollision(BaseCheck):
    """ A check that all ports are connected """
    def __init__(self):
        self.port_mappings = {}

    @classmethod
    def get_identifiers(self) -> Dict[str, CheckSeverity]:
        """ Returns identifiers produced here."""
        return {
            "array-port-collision": CheckSeverity.ERROR
        }

    def run(self, result: CheckResult, model: Topology, extras: List[str]) -> CheckResult:
        """ Run the check """
        for component in model.get_comp_list():
            for port in component.get_ports():
                target_port = port.get_target_port()
                target_component = port.get_target_comp()

                # Only a check for connected ouput ports
                if port.get_direction().lower() == "input" or target_port is None or target_component is None:
                    continue
                target_comp_obj = model.get_comp_by_name(target_component)
                target_port_obj = target_comp_obj.get_port_by_name(target_port, port.get_target_num())
                target_max_num = target_port_obj.get_max_number()
                # Also ignore max numbers of 1, as they aren't arrays
                if target_max_num is None or int(target_max_num) <= 1:
                    continue
                standard_id = BaseCheck.get_standard_identifier(model, target_comp_obj, target_port_obj)
                if standard_id in self.port_mappings:
                    result.add_problem("array-port-collision", "has colliding inputs",
                                       model, target_comp_obj, target_port_obj)
                self.port_mappings[standard_id] = target_comp_obj
        return result

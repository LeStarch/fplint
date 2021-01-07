import abc
import re
import sys
import inspect
from enum import Enum
import itertools

from typing import Type, List, Union, Dict

from fprime_ac.models.Topology import Topology
from fprime_ac.models.Component import Component
from fprime_ac.models.Port import Port

class CheckSeverity(Enum):
    """ Severity of checks """
    WARNING = 0
    ERROR = 1
    FATAL = 2 # Stops check

class CheckResult:
    """ Enumeration capturing linting results """
    def __init__(self, severity_map: Dict[str,CheckSeverity]):
        """ Initialize check result with severity mapping

        Args:
            severiy_map: map of identifiers to severities
        """
        self.severities = severity_map
        self.problems = []

    def add_problem(self, ident: str, message: str, top: Topology=None, comp: Component=None, port: Port=None):
        """ Adds the specified problem with the given message

        Registers a problem detected with a check. These identifiers map to the WARNING/ERROR mappings passed in at
        construction time. If top/comp/port is specified it will be prepended to the message, and used as part of the
        masking of problems as configured.

        Args:
            ident: identifier of problem. Must be in setup map. Used for printing and masking of errors.
            message: message to output with output. Not masked.
            top: (optional) topology for module specification
            comp: (optional) component for module specification
            port: (optional) port for module specification
        """
        assert ident in self.severities, "{} is not in list of expected identifiers".format(ident)
        severity = self.severities[ident]
        self.problems.append(
            {
                "severity": severity,
                "identifier": ident,
                "message": message,
                "module": BaseCheck.get_standard_identifier(top, comp, port)
            })

    def get_filtered_problems(self, exclusions: List[Dict[str, Union[str, List[Dict[str, Union[str,re.Pattern]]]]]]):
        """ Filter down the problems to non-excluded """
        def is_excluded(problem):
            """ Check if a problem is excluded at all """
            for exclusion in exclusions:
                if not problem.get("identifier") == exclusion.get("identifier"):
                    continue
                specifiers = [property.get("specifier") for property in exclusion.get("properties", []) if "specifier" in property]
                for specifier in specifiers:
                    if specifier.search(problem.get("module")):
                        return True
            return False
        problems = [problem for problem in self.problems if not is_excluded(problem)]
        return problems

    @staticmethod
    def get_problem_message(problem):
        """ Returns a problem message """
        return "[{}] {}: {} found issue {}".format(problem.get("severity").name,
                                                   problem.get("identifier"),
                                                   problem.get("module"),
                                                   problem.get("message"))


class BaseCheck(abc.ABC):

    @staticmethod
    def get_standard_identifier(topology: Topology, component: Component=None, port:Port=None):
        """ Get the standard identifier of a model object"""
        tokens = [item.get_name() for item in [topology, component, port] if item is not None]
        identifier = ".".join(tokens)
        if port is not None:
            identifier += ":{}".format(port.get_source_num())
        return identifier

    @classmethod
    def get_name(cls):
        """ Returns the name of this checker. Default implementation returns class name. """
        return cls.__name__

    @classmethod
    @abc.abstractmethod
    def get_identifiers(self) -> Dict[str, str]:
        """ Return a mapping from identifier to severity """
        raise NotImplemented("Must implement this method of the checker")

    @abc.abstractmethod
    def run(self, result: CheckResult, model: Topology) -> CheckResult:
        """ Executes the check class actions.  Implement this for a new check"""
        raise NotImplemented("Must implement this method of the checker")

    @classmethod
    def get_all_identifiers(cls, excluded: List[str] = None):
        """ Get all known lint identifiers """
        checkers = cls.get_checkers(excluded)
        return itertools.chain.from_iterable([checker.get_identifiers().keys() for checker in checkers])

    @classmethod
    def get_checkers(cls, excluded: List[str] = None, candidate: Type = None) -> List[Type["BaseCheck"]]:
        """ Recurses through subclasses looking for non-abstract implementations """
        excluded = excluded if excluded is not None else []
        candidate = candidate if candidate is not None else cls
        # Check current class for non-abstract and not excluded
        checkers = [candidate] if not inspect.isabstract(candidate) and candidate.get_name() not in excluded else []
        for sub in candidate.__subclasses__():
            checkers.extend(cls.get_checkers(excluded, sub))
        return checkers

    @classmethod
    def run_all(cls, model: Topology, excluded: List[str] = None, filters: List[str] = None):
        """ Runs all known checks"""
        excluded = excluded if excluded is not None else []
        filters = filters if filters is not None else []
        checkers = cls.get_checkers(excluded)
        print("[FP-LINT] Found {} checks".format(len(checkers)))
        all_clear = True
        for checker in checkers:
            try:
                print("[FP-LINT] Running check '{}'".format(checker.get_name()))
                result = CheckResult(checker.get_identifiers())
                result = checker().run(result, model)
                problems = result.get_filtered_problems(filters)
                for problem in problems:
                    print(result.get_problem_message(problem), file=sys.stderr)
                all_clear = all_clear and not problems
            except Exception as exc:
                print("[ERROR] {} failed: {}".format(checker.get_name(), exc), file=sys.stderr)
                all_clear = False
                raise
            return all_clear


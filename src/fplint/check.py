""" Checks definitions for the linters

Specifies the base checks for the linter. This provides a notifier object "CheckResult", a enum of severities
"CheckSeverity" and abstract base check class to implement children of "CheckBase".
"""
import abc
import re
import sys
import inspect
from enum import Enum
import itertools
from typing import Type, List, Union, Dict

# Load the model types through patcher
from fplint.model.patcher import Port, Component, Topology


class CheckSeverity(Enum):
    """ Severity of checks """
    WARNING = 0
    ERROR = 1


class CheckResult:
    """
    Notification object used when an error occurs. It takes in identifiers, messages, and models where possible to note
    an error occurred and provide standard reporting formats of messages. In order to setup the check result, the
    "CheckBase" class will provide a mapping of identifiers to severity. This is such that callers need only specify the
    identifier and the message.
        """
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
                "module": CheckBase.get_standard_identifier(top, comp, port)
            })

    def get_filtered_problems(self, filters: List[Dict[str, Union[str, List[re.Pattern]]]]) -> List[dict]:
        """ Returns list of notified problems filtered through the filtered list

        Args:
            filters: filters used to match problems such that they are ignored

        Returns:
            list of problems that are not filtered-out
        """
        def is_excluded(problem):
            """ Check if a problem is excluded at all """
            for filt in filters:
                # Not a matching identifier
                if not problem.get("identifier") == filt.get("identifier"):
                    continue
                specifiers = filt.get("specifiers")
                for specifier in specifiers:
                    if specifier.search(problem.get("module")):
                        return True
            return False
        problems = [problem for problem in self.problems if not is_excluded(problem)]
        return problems

    @staticmethod
    def get_problem_message(problem: dict) -> str:
        """ Formats the standard problem message in a repoducible way """
        return "[{}] {}: {} found issue {}".format(problem.get("severity").name,
                                                   problem.get("identifier"),
                                                   problem.get("module"),
                                                   problem.get("message"))


class CheckBase(abc.ABC):
    """
    Base object for all checks in the system. This provides a set of helper methods to help implement checks as well as
    a set of abstract methods to define the format of the check. It can also run all known check by inspecting
    subclasses of the base check to find checks.
    """

    @staticmethod
    def get_standard_identifier(topology: Topology = None, component: Component = None, port:Port = None) -> str:
        """ Takes the model components and returns a str standard identifier

        Args:
            topology: topology model, ignored if None
            component: component model, ignored if None
            port: port model, ignored if None

        Returns:
            [top name].[comp name].[port name:port number]
        """
        tokens = [item if isinstance(item, str) else item.get_name() for item in [topology, component, port] if item is not None]
        identifier = ".".join(tokens)
        if port is not None:
            identifier += ":{}".format(port.get_source_num())
        return identifier

    @classmethod
    @abc.abstractmethod
    def get_identifiers(self) -> Dict[str, CheckSeverity]:
        """ Return a mapping from identifier to severity

        Gets a set of identifiers produced by this check, and the severity of that identifier. These are used in two
        places:

        1. It is stored in the CheckResult so users need not pass in the severity with the notify call
        2. It is used in the list of "know identifiers" used for configuration

        Returns:
            Map of str to CheckSeverity for every identifier provides by this system
        """
        raise NotImplemented("Must implement this method of the checker")

    @staticmethod
    def get_extra_arguments():
        """ Implement this class in sub children if you need extra arguments"""
        return {}

    @abc.abstractmethod
    def run(self, result: CheckResult, model: Topology, extras: List[str]):
        """ Run the check

        This is up to the base class. The base class will be provided a toplogy model, and a list of "extra" arguments
        it needs. It can register problems to the provided check result.

        Args:
            result: call result.add_problem() to report a linting problem seen
            model: topology model to lint
            extras: extra arguments when asked
        """
        raise NotImplemented("Must implement this method of the checker")

    @classmethod
    def get_all_identifiers(cls, excluded: List[str] = None):
        """ Returns all known identifiers of all known implementers

        This is passed to configuration to ensure that all filters are valid.
        """
        checkers = cls.get_checkers(excluded)
        return itertools.chain.from_iterable([checker.get_identifiers().keys() for checker in checkers])

    @classmethod
    def get_all_extra_args(cls, excluded: List[str] = None) -> Dict[str,Dict[str, str]]:
        """ Get all known lint identifiers by recursing through sub children """
        all_args = {}
        checkers = cls.get_checkers(excluded)
        for checker in checkers:
            all_args.update(checker.get_extra_arguments())
        return all_args

    @classmethod
    def get_checkers(cls, excluded: List[str] = None, candidate: Type = None) -> List[Type["CheckBase"]]:
        """ Recursively looks for known checkers found in the system """
        excluded = excluded if excluded is not None else []
        candidate = candidate if candidate is not None else cls
        # Check current class for non-abstract and not excluded
        checkers = [candidate] if not inspect.isabstract(candidate) and candidate.__name__ not in excluded else []
        for sub in candidate.__subclasses__():
            checkers.extend(cls.get_checkers(excluded, sub))
        return checkers

    @classmethod
    def run_all(cls, model: Topology, excluded: List[str] = None, filters: List[str] = None, arguments=None):
        """ Runs all known checks"""
        excluded = excluded if excluded is not None else []
        filters = filters if filters is not None else []
        checkers = cls.get_checkers(excluded)
        print("[FP-LINT] Found {} checks".format(len(checkers)))
        all_clear = True
        for checker in checkers:
            try:
                needed_args = [arg.replace("-", "_") for arg in checker.get_extra_arguments().keys()]
                filled_args = [getattr(arguments, needed, None) for needed in needed_args if getattr(arguments, needed, None) is not None]
                if needed_args and arguments is None or len(needed_args) != len(filled_args):
                    print("[FP-LINT] '{}' missing needed args. Skipping".format(checker.__name__), file=sys.stderr)
                    continue
                print("[FP-LINT] Running check '{}'".format(checker.__name__))
                result = CheckResult(checker.get_identifiers())
                result = checker().run(result, model, filled_args)
                problems = result.get_filtered_problems(filters)
                for problem in problems:
                    print(result.get_problem_message(problem), file=sys.stderr)
                all_clear = all_clear and not problems
            except Exception as exc:
                print("[ERROR] {} failed: {}".format(checker.__name__, exc), file=sys.stderr)
                all_clear = False
        return all_clear


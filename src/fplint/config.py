""" Loads the XML structure into an easily accessible system model

Loads the XML structure of the system ready for linting and analysis. The configuration format of the file looks like
the following in order to specify which checks to exclude and which identifiers to filter.  Filtered identifiers are
run, but the output is discarded and they do not affect the status code of execution.  Exclusions discard running checks
all together.

YAML format:
filters:
  <identifier>:
      - specifier: regex string for matching identifier
      - specifier: regex string for matching identifier
  <identifier>:
exclusions:
  - <check class name>
  - <check class name>

The returned configuration format will look similar, but is normalized such that it is easy to use.

{"exclusions": [],
 "filters": [{"identifier": <identifier name>, "specifiers": [re.Patterns]}, ...]
"""
import re
from typing import Union, List, Dict

import yaml


def load_configuration(yml_file, known_idents: List[str]) -> Dict[str,List[Dict[str, Union[str, List[re.Pattern]]]]]:
    """ Loads the configuration YAML file passed in

    Loads the YAML configuration for excluding checks and filtering out various specific identifiers w.r.t their
    component instance.

    Args:
        yml_file: YAML file opened as "r" by argparse
        known_idents: list of known identifiers descovered by polling checks

    Returns:

    """
    try:
        config = {} if yml_file is None else yaml.safe_load(yml_file.read())
    except yaml.YAMLError as yer:
        raise ConfigurationException("Failed to YAML configuration {}: {}".format(yml_file.name, yer)) from yer
    identifiers = [__homogenize_filter(known_idents, ident, prop) for ident, prop in config.get("filters", {}).items()]
    config["filters"] = identifiers
    return config


def __homogenize_filter(idents: List[str], identifier: str, properties: List[dict]) -> Dict[str, Union[str, List[re.Pattern]]]:
    """ Remake all exclusion formats to look the same to downstream code

    Args:
        idents: list of valid identifiers
        identifier: identifier to check in above list and add to our object
        properties: list of property objects from configuration. Each will be coupled with the identifier.

    Returns: reformatted exclusion object of form {"identifier": "identifier-123", "specifiers": []}
    """
    if identifier not in idents:
        raise ConfigurationException("Unknown identifier '{}' specified".format(identifier))
    properties = [{}] if not properties else properties
    specifiers = [re.compile(prop.get("specifier", ".*")) for prop in properties]
    return {"identifier": identifier, "specifiers": specifiers}


class ConfigurationException(Exception):
    pass
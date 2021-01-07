""" Loads the XML structure into an easily accessible system model

Loads the XML structure of the system ready for linting and analysis.
"""
import re
import itertools
from typing import List
from pathlib import Path

import yaml

from fplint.factory import mega_topology_loader


def load_model(xml_file : Path):
    """ Load an XML file from the above path"""
    try:
        model = mega_topology_loader(xml_file)
    except Exception as exc:
        raise LoadException("Failed to load topology model {} with error {}".format(xml_file, exc)) from exc
    return model


def homogenize_filters(idents: List[str], identifier: str, properties: List[dict]) -> List[dict]:
    """ Remake all exclusion formats to look the same to downstream code

    Exclusions can be a string (e.g. "identifier-123") to exclude identifiers completely, a dictionary of form
    {"identifier-123": {properties}} to exclude identifiers with certain restrictions, or a dictionary of the form
    {"identifier": "identifier-123", properties...} to exclude again with certain restrictions. This function reformats
    all options to the last one.  If an identifier does not exist, it will raise an error.

    Args:
        idents: list of valid identifiers
        exclusion: exclusion object.

    Returns: reformatted exclusion object of form {"identifier": "identifier-123", "specifier": regex}
    """
    properties = [{}] if properties is None else properties
    properties = [{"specifier": re.compile(property.get("specifier", ".*"))} for property in properties]
    return [{"identifier": identifier, "properties": properties}]


def load_configuration(yml_file, identifiers: List[str]):
    """ Load configuration data"""
    try:
        config = {} if yml_file is None else yaml.safe_load(yml_file.read())
    except yaml.YAMLError as ymlerr:
        raise LoadException("Failed to load configuration {} with error {}".format(yml_file.name, ymlerr)) from ymlerr
    config["filters"] = list(itertools.chain.from_iterable([homogenize_filters(identifiers, identifier, properties) for identifier, properties in config.get("filters", {}).items()]))
    return config


class LoadException(Exception):
    pass
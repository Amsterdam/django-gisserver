"""Exceptions for the WFS operations.

Not all exception codes are listed here, only the one that
apply to the current set of supported operations.
"""
from django.template.loader import render_to_string


class OWSException(Exception):
    """Base class for XML based exceptions in this module."""

    status_code = 400  # Most common code in spec
    service = None
    version = "2.0.0"
    code = None
    text_template = None

    def __init__(self, locator, text=None, code=None):
        text = text or self.text_template.format(code=self.code, locator=locator)
        super().__init__(text)
        self.locator = locator
        self.text = text
        self.code = code or self.code

    def as_xml(self):
        return render_to_string(
            [
                f"gisserver/{self.service.lower()}/{self.version}/exception.xml",
                f"gisserver/{self.version}/exception.xml",
            ],
            {"self": self},
        )

    def __html__(self):
        return self.as_xml()


class WFSException(OWSException):
    service = "WFS"


class OperationNotSupported(WFSException):
    status_code = 400
    code = "OperationNotSupported"
    text_template = "Operation is not implemented."


class MissingParameterValue(WFSException):
    status_code = 400
    code = "MissingParameterValue"
    text_template = "Missing required '{locator}' parameter."


class InvalidParameterValue(WFSException):
    status_code = 400
    code = "InvalidParameterValue"
    text_template = "Invalid value for '{locator}' parameter."


class VersionNegotiationFailed(WFSException):
    status_code = 400
    code = "VersionNegotiationFailed"
    text_template = "'ACCEPTVERSIONS' contains an invalid version number."

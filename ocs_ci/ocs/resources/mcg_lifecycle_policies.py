from abc import ABC
import datetime
import uuid
import xml.etree.ElementTree as ET
import xml.dom.minidom


class LifecyclePolicy:
    """
    A class for handling MCG lifecycle policy config parsing

    """

    def __init__(self, *args):
        """
        Constructor method for the class

        Args:
            *args: One or more LifecycleRule instances or a list of LifecycleRule instances

        """
        if len(args) == 1 and isinstance(args[0], list):
            self.rules = args[0]
        else:
            self.rules = args

        for rule in self.rules:
            if not isinstance(rule, LifecycleRule):
                raise TypeError(f"Rule {rule} is not of type LifecycleRule")

    def as_dict(self):
        """
        Returns the lifecycle policy as a dictionary that matches
        the expected S3 lifecycle policy JSON format.

        Note that the objects in self.rules are expected to have their own
        as_dict() implementation.
        """
        return {"Rules": [rule.as_dict() for rule in self.rules]}

    def as_xml(self):
        """
        Convert the lifecycle policy to XML format

        Returns:
            str: XML string representation of the lifecycle policy
        """

        def create_element(parent, key, value):
            if isinstance(value, dict):
                elem = ET.SubElement(parent, key)
                for k, v in value.items():
                    create_element(elem, k, v)
            elif isinstance(value, list):
                for item in value:
                    item_elem = ET.SubElement(parent, key)
                    if isinstance(item, dict):
                        for k, v in item.items():
                            create_element(item_elem, k, v)
            else:
                elem = ET.SubElement(parent, key)
                if value is not None:
                    elem.text = (
                        str(value).lower() if isinstance(value, bool) else str(value)
                    )

        root = ET.Element("LifecycleConfiguration")
        for rule in self.rules:
            rule_el = ET.SubElement(root, "Rule")
            for key, value in rule.as_dict().items():
                create_element(rule_el, key, value)

        # Prettify
        raw_xml_string = ET.tostring(root, encoding="unicode")
        parsed = xml.dom.minidom.parseString(raw_xml_string)
        xml_string = parsed.toprettyxml(indent="  ")

        return xml_string

    def __str__(self):
        return self.as_dict().__str__()

    def __repr__(self):
        return self.__str__()


class LifecycleFilter:
    """
    A class for handling S3 lifecycle filter parsing

    """

    def __init__(self, prefix=None, tags=None, minBytes=None, maxBytes=None):
        """
        Constructor method for the class

        Args:
            prefix (str): Prefix of the target objects
            tags (list): A list of dictionaries specifying the tags of the target objects
            minBytes (int): Minimum size of the objects
            maxBytes (int): Maximum size of the objects

        NOTE: Setting minBytes and maxBytes will fail when applying the lifecycle config
              because the current boto3 version and awscli version on the pod are not compatible
              with the newer AWS API.
        """
        self.prefix = prefix
        self.tags = tags
        self.minBytes = minBytes
        self.maxBytes = maxBytes

    def as_dict(self):
        """
        Returns the rule as a dictionary that matches
        the expected S3 lifecycle policy JSON format
        """
        list_of_tag_dicts = []

        # Initially add any criteria under the "And" key
        filter_dict = {"And": {}}
        if self.prefix:
            filter_dict["And"]["Prefix"] = self.prefix
        if self.minBytes:
            filter_dict["And"]["ObjectSizeGreaterThan"] = self.minBytes
        if self.maxBytes:
            filter_dict["And"]["ObjectSizeLessThan"] = self.maxBytes
        if self.tags:
            # Convert tags from a dictionary to a list of dictionaries in expected format
            for key, val in self.tags.items():
                list_of_tag_dicts.append({"Key": key, "Value": val})
            filter_dict["And"]["Tags"] = list_of_tag_dicts

        # If there is no filter criteria, set an empty dict
        if len(filter_dict["And"]) == 0:
            filter_dict = {}

        # If there's only one criteria and it's not tags, remove the "And" key
        elif len(filter_dict["And"]) == 1 and len(list_of_tag_dicts) == 0:
            key, val = next(iter(filter_dict["And"].items()))
            filter_dict = {key: val}

        # If there's only one tag, remove the "And" key and place
        # the one tag as a dict under "Tag" instead of inside a list under "Tags"
        elif len(filter_dict["And"]) == 1 and len(list_of_tag_dicts) == 1:
            filter_dict["And"]["Tag"] = list_of_tag_dicts[0]
            del filter_dict["And"]["Tags"]
            filter_dict = filter_dict["And"]

        return filter_dict

    def __str__(self):
        return self.as_dict().__str__()

    def __repr__(self):
        return self.__str__()


class LifecycleRule(ABC):
    """
    An abstract class for handling MCG lifecycle rule parsing

    """

    def __init__(self, filter=LifecycleFilter(), is_enabled=True):
        """
        Constructor method for the class

        Args:
            filter (LifecycleFilter): Optional object filter
            is_enabled (bool): Whether the rule is enabled or not

        """
        self.filter = filter
        self.is_enabled = is_enabled
        self._id = f"rule-{uuid.uuid4().hex[:8]}"

    def as_dict(self):
        """
        Returns the rule as a dictionary that matches
        the expected S3 lifecycle policy JSON format
        """
        rule_dict = {
            "Filter": self.filter.as_dict(),
            "ID": self._id,
            "Status": "Enabled" if self.is_enabled else "Disabled",
        }

        return rule_dict

    def __str__(self):
        return self.as_dict().__str__()

    def __repr__(self):
        return self.__str__()

    @property
    def id(self):
        return self._id


class ExpirationRule(LifecycleRule):
    """
    A class for handling the parsing of an MCG object expiration rule

    """

    def __init__(
        self,
        days=None,
        filter=LifecycleFilter(),
        use_date=False,
        is_enabled=True,
    ):
        """
        Constructor method for the class

        Args:
            days (int): Number of days after which the objects will expire
            filter (LifecycleFilter): Optional object filter
            use_date (bool): Whether to set a a date instead of the number of days
            is_enabled (bool): Whether the rule is enabled or not
        """
        super().__init__(filter=filter, is_enabled=is_enabled)
        self.days = days
        self.use_date = use_date

    def as_dict(self):
        """
        Returns the rule as a dictionary that matches
        the expected S3 lifecycle policy JSON format
        """
        rule_dict = super().as_dict()

        d = {}

        if self.days:
            key = "Date" if self.use_date else "Days"
            value = (
                (datetime.datetime.now() + datetime.timedelta(days=self.days)).strftime(
                    "%Y-%m-%d"
                )
                if self.use_date
                else self.days
            )
            d[key] = value

        rule_dict["Expiration"] = d
        return rule_dict


class ExpiredObjectDeleteMarkerRule(LifecycleRule):
    """
    A class for handling the parsing of an MCG expired object delete marker rule

    Note the separation from ExpirationRule is due to the fact that
    Expiration.ExpiredObjectDeleteMarker cannot be specified with
    Days or Date in a Lifecycle Expiration Policy:
    https://docs.aws.amazon.com/AmazonS3/latest/API/API_LifecycleExpiration.html
    """

    def __init__(
        self,
        filter=LifecycleFilter(),
        is_enabled=True,
        expire_object_delete_marker=True,
    ):
        """
        Constructor method for the class

        Args:
            filter (LifecycleFilter): Optional object filter
            is_enabled (bool): Whether the rule is enabled or not
            expire_object_delete_marker (bool): Whether to expire the object delete marker
        """
        super().__init__(filter=filter, is_enabled=is_enabled)
        self.expire_object_delete_marker = expire_object_delete_marker

    def as_dict(self):
        rule_dict = super().as_dict()
        rule_dict["Expiration"] = {
            "ExpiredObjectDeleteMarker": self.expire_object_delete_marker
        }
        return rule_dict


class AbortIncompleteMultipartUploadRule(LifecycleRule):
    """
    A class for handling the parsing of an MCG object expiration rule
    """

    def __init__(
        self,
        days_after_initiation,
        filter=LifecycleFilter(),
        is_enabled=True,
    ):
        """
        Constructor method for the class

        Args:
            days_after_initiation (int): Number of days after which the multipart upload will be aborted
            filter (LifecycleFilter): Optional object filter
            is_enabled (bool): Whether the rule is enabled or not
        """
        super().__init__(filter=filter, is_enabled=is_enabled)
        self.days_after_initiation = days_after_initiation

    def as_dict(self):
        """
        Returns the rule as a dictionary that matches
        the expected S3 lifecycle policy JSON format
        """
        rule_dict = super().as_dict()
        rule_dict["AbortIncompleteMultipartUpload"] = {
            "DaysAfterInitiation": self.days_after_initiation
        }
        return rule_dict


class NoncurrentVersionExpirationRule(LifecycleRule):
    """
    A class for handling the parsing of an MCG non-current version expiration rule
    """

    def __init__(
        self,
        non_current_days=None,
        newer_non_current_versions=None,
        filter=LifecycleFilter(),
        is_enabled=True,
    ):
        """
        Constructor method for the class

        Args:
            non_current_days (int): Number of days after which the non-current version will expire
            newer_non_current_versions (int): Number of newer non-current versions to retain
            filter (LifecycleFilter): Optional object filter
            is_enabled (bool): Whether the rule is enabled or not
        """
        super().__init__(filter=filter, is_enabled=is_enabled)
        self.non_current_days = non_current_days
        self.newer_non_current_versions = newer_non_current_versions
        if not self.non_current_days and not self.newer_non_current_versions:
            raise ValueError(
                "Either non_current_days or newer_non_current_versions must be set"
            )

    def as_dict(self):
        """
        Returns the rule as a dictionary that matches
        the expected S3 lifecycle policy JSON format
        """
        rule_dict = super().as_dict()

        d = {}
        if self.non_current_days is not None:
            d["NoncurrentDays"] = self.non_current_days
        if self.newer_non_current_versions is not None:
            d["NewerNoncurrentVersions"] = self.newer_non_current_versions
        rule_dict["NoncurrentVersionExpiration"] = d

        return rule_dict

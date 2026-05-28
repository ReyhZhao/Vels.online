"""Assemble Wazuh <rule level="0"> XML for an ExceptionRule record."""
import xml.etree.ElementTree as ET


def rule_to_xml(rule) -> str:
    """Return a formatted Wazuh rule XML string for *rule*.

    Produces a <rule level="0"> that silences the trigger rule.
    One optional <match> block and one optional <field> block are supported.
    For org-scoped rules, an agent.name <field> is included when agent_name is set.
    """
    root = ET.Element("rule", id=str(rule.wazuh_rule_id), level="0")

    desc = ET.SubElement(root, "description")
    desc.text = rule.description or f"Exception rule {rule.wazuh_rule_id}"

    if rule.trigger_rule_id:
        sid = ET.SubElement(root, "if_sid")
        sid.text = str(rule.trigger_rule_id)

    if rule.match_value:
        match = ET.SubElement(root, "match")
        match.text = rule.match_value

    if rule.field_name and rule.field_value:
        field_elem = ET.SubElement(
            root, "field",
            name=rule.field_name,
            **({"negate": "no", "type": rule.field_type} if rule.field_type else {}),
        )
        field_elem.text = rule.field_value

    if rule.scope == "org" and rule.agent_name:
        agent_elem = ET.SubElement(root, "field", name="agent.name")
        agent_elem.text = rule.agent_name

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def rule_file_path(rule) -> str:
    """Return the repo-relative file path for this rule's XML file."""
    if rule.scope == "global" or rule.organisation is None:
        return "wazuh/files/rules/global_exceptions.xml"
    return f"wazuh/files/rules/{rule.organisation.slug}_exceptions.xml"

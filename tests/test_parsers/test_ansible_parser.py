"""Tests for Ansible parser normalization behavior."""

from __future__ import annotations

import unittest

from parsers.ansible_parser import parse_ansible


class AnsibleParserTests(unittest.TestCase):
    def test_parse_ansible_returns_empty_list_when_content_missing(self) -> None:
        self.assertEqual(parse_ansible("site.yml", None), [])

    def test_parse_ansible_supports_multi_document_playbooks(self) -> None:
        raw = b"""---
- hosts: app
  tasks:
    - name: Install packages
      ansible.builtin.package:
        name: nginx
---
hosts: app
tasks:
  - name: Restart service
    ansible.builtin.service:
      name: nginx
      state: restarted
"""

        changes = parse_ansible("site.yml", raw)

        self.assertEqual([change.resource_id for change in changes], ["Install packages", "Restart service"])
        self.assertTrue(all(change.tool == "ansible" for change in changes))

    def test_parse_ansible_falls_back_to_indexed_task_names_for_non_mapping_tasks(self) -> None:
        raw = b"""hosts: app
tasks:
  - restart nginx
  - name: Verify service
    ansible.builtin.command: systemctl status nginx
"""

        changes = parse_ansible("site.yml", raw)

        self.assertEqual([change.resource_id for change in changes], ["task-1", "Verify service"])
        self.assertIn("task-1", changes[0].summary)


if __name__ == "__main__":
    unittest.main()

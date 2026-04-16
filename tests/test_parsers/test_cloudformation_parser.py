"""Tests for CloudFormation parser behavior."""

from __future__ import annotations

import unittest

from parsers.cloudformation_parser import parse_cloudformation


class CloudFormationParserTests(unittest.TestCase):
    def test_parse_cloudformation_supports_intrinsic_yaml_tags(self) -> None:
        raw = b"""AWSTemplateFormatVersion: '2010-09-09'
Resources:
  AppBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub '${AWS::StackName}-app'
Outputs:
  BucketArn:
    Value: !GetAtt AppBucket.Arn
"""

        changes = parse_cloudformation("galaxy-metl-sg-rules.yaml", raw)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].tool, "cloudformation")
        self.assertEqual(changes[0].resource_id, "resource/AppBucket")


if __name__ == "__main__":
    unittest.main()

terraform {
  required_providers {
    external = {
      source = "hashicorp/external"
      version = "2.3.5"
    }
  }
}
data "external" "qualification" {
  program = ["/usr/local/bin/python", "/opt/qualification/provider_probe.py"]
}
resource "terraform_data" "synthetic" {
  input = "qualification-only-no-apply"
}
output "probe" { value = data.external.qualification.result }

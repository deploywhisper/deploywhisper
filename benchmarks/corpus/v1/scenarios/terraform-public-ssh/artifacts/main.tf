resource "aws_security_group_rule" "demo_public_ssh" {
  type = "ingress"
  cidr_blocks = ["0.0.0.0/0"]
  from_port = 22
  to_port = 22
  protocol = "tcp"
  security_group_id = "sg-demo"
}

FROM ghcr.io/opentofu/opentofu@sha256:dfbc3f0a8bed0adfa2cf49ff418f158afe24080eea6d6e748db8799fc4553db6 AS tool
FROM python@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89 AS dependencies
COPY --from=tool /usr/local/bin/tofu /usr/local/bin/tofu
RUN echo 'd5c690023baebe8bf2cfb2062e292186f4797a173db22c973bd9de45cb68a62f  /usr/local/bin/tofu' | sha256sum -c - && cp -L /usr/local/bin/python /usr/local/bin/python-pinned && rm /usr/local/bin/python && mv /usr/local/bin/python-pinned /usr/local/bin/python
COPY tests/fixtures/infra_automation/qualification/16_13/source /opt/deploywhisper/source
RUN cd /opt/deploywhisper/source && tofu init -backend=false -input=false && tofu providers mirror /opt/mirror && rm -rf .terraform
RUN python -c "import pathlib,zipfile; root=pathlib.Path('/opt/mirror/registry.opentofu.org/hashicorp/external'); package=next(root.glob('*.zip')); target=root/'2.3.5/linux_arm64'; target.mkdir(parents=True); zipfile.ZipFile(package).extractall(target); [(p.chmod(0o555)) for p in target.iterdir()]; package.unlink()" && echo 'f9994ee228b86d34c289d858af46f758921f34393a27a1bb5677761c08228f50  /opt/mirror/registry.opentofu.org/hashicorp/external/2.3.5/linux_arm64/terraform-provider-external' | sha256sum -c -
FROM dependencies AS qualification
COPY tests/fixtures/infra_automation/qualification/16_13/probe.py tests/fixtures/infra_automation/qualification/16_13/provider_probe.py tests/fixtures/infra_automation/qualification/16_13/tofurc /opt/deploywhisper/
COPY infra_automation/runner/bootstrap.py /opt/deploywhisper/bootstrap.py
RUN python -c "import pathlib,hashlib,json; files=[pathlib.Path('/usr/local/bin/python'),pathlib.Path('/usr/local/bin/tofu'),*pathlib.Path('/opt/deploywhisper').rglob('*'),*pathlib.Path('/opt/mirror').rglob('*')]; value={str(p):'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}; pathlib.Path('/opt/deploywhisper/pins.json').write_text(json.dumps(value,sort_keys=True))" && chmod -R a-w /opt/deploywhisper /opt/mirror
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/python", "-I", "/opt/deploywhisper/bootstrap.py"]

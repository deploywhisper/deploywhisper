FROM ghcr.io/opentofu/opentofu@sha256:dfbc3f0a8bed0adfa2cf49ff418f158afe24080eea6d6e748db8799fc4553db6 AS tool
FROM python@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89
COPY --from=tool /usr/local/bin/tofu /usr/local/bin/tofu
RUN pip install --no-cache-dir cryptography==50.0.2
COPY isolation/source /opt/qualification/source
RUN cd /opt/qualification/source && tofu init -backend=false -input=false && tofu providers mirror /opt/mirror && rm -rf .terraform
RUN python -c "import pathlib,zipfile; root=pathlib.Path('/opt/mirror/registry.opentofu.org/hashicorp/external'); package=next(root.glob('*.zip')); target=root/'2.3.5/linux_arm64'; target.mkdir(parents=True); zipfile.ZipFile(package).extractall(target); [(p.chmod(0o555)) for p in target.iterdir()]; package.unlink()" && chmod -R a-w /opt/qualification /opt/mirror
COPY isolation/probe.py isolation/provider_probe.py isolation/tofurc /opt/qualification/
COPY real_custody /opt/custody
COPY receiver/prototype.py /opt/custody/receiver.py
RUN chmod -R a-w /opt/qualification /opt/custody /opt/mirror
ENV TF_IN_AUTOMATION=1 TF_INPUT=0 TF_CLI_CONFIG_FILE=/opt/qualification/tofurc
USER 10001:10001
ENTRYPOINT ["python", "/opt/qualification/probe.py"]

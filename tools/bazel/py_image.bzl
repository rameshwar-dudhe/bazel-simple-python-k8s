"""Reusable macro: turn a py_binary into an OCI image.

One macro, used by every service. When the platform team wants to change the
base image, add a label, or switch the layering strategy, it is a one-line
change here instead of a change in every service's BUILD file. This is the
Bazel equivalent of a reusable CircleCI command/orb.

Targets created by py_service_image(name = "image", ...):

  :image            the OCI image (oci_image)
  :image_tarball    docker-loadable tar   -> bazel run //services/api:image_tarball
  :image_push       bazel-native push     -> bazel run //services/api:image_push
  :image_layer      the pkg_tar app layer (useful when debugging image content)
"""

load("@rules_oci//oci:defs.bzl", "oci_image", "oci_load", "oci_push")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

def py_service_image(
        name,
        binary,
        repository,
        base = "@python_base",
        workdir = "/app"):
    """Package a py_binary (with all its runfiles) into an OCI image.

    Args:
      name: base name for the generated targets.
      binary: the py_binary label to containerise.
      repository: default push repository (overridable at push time with
        `bazel run //target:image_push -- --repository ...`).
      base: base image label pulled by digest in MODULE.bazel.
      workdir: directory the app is unpacked into.
    """

    # pkg_tar flattens to <workdir>/<binary name> + <workdir>/<name>.runfiles/
    launcher = binary.split(":")[-1]

    # The app layer: the launcher plus its complete runfiles tree (our code,
    # the hermetic CPython, and any pip wheels the binary depends on).
    pkg_tar(
        name = name + "_layer",
        srcs = [binary],
        include_runfiles = True,
        package_dir = workdir,
        strip_prefix = ".",
        # Reproducible layers: fixed (portable) timestamps and ownership.
        # Same inputs => same digest => pushing an unchanged service is a no-op
        # in the registry.
        portable_mtime = True,
        owner = "0.0",
    )

    oci_image(
        name = name,
        base = base,
        entrypoint = ["{}/{}".format(workdir, launcher)],
        env = {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "RUNFILES_DIR": "{}/{}.runfiles".format(workdir, launcher),
        },
        labels = {
            "org.opencontainers.image.source": "https://github.com/acme/pyplatform",
            "org.opencontainers.image.title": name,
        },
        tars = [":" + name + "_layer"],
        visibility = ["//visibility:public"],
        workdir = workdir,
    )

    # `bazel run //services/api:image_tarball` loads the image into the local
    # docker daemon as <repository>:local - that is what the k8s demo deploys.
    oci_load(
        name = name + "_tarball",
        image = ":" + name,
        repo_tags = [repository + ":local"],
        visibility = ["//visibility:public"],
    )

    # Bazel-native push. The release tool (//tools/release) uses crane instead,
    # because release tags are computed at release time from the manifest; this
    # target exists for one-off manual pushes and for comparison.
    oci_push(
        name = name + "_push",
        image = ":" + name,
        remote_tags = ["latest"],
        repository = repository,
        visibility = ["//visibility:public"],
    )

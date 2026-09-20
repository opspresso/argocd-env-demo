import json
import unittest

from workload_policy import policy_errors, target_platform


def manifest(kind, spec, name="test"):
    return json.dumps({"apiVersion": "v1", "kind": kind, "metadata": {"name": name}, "spec": spec})


class WorkloadPolicyTests(unittest.TestCase):
    def test_eks_is_the_default_and_preserves_chart_policy(self):
        self.assertEqual(target_platform({"appset": "apps/example.yaml"}, {}), "eks")
        self.assertEqual(target_platform({"appset": "apps/eks/example.yaml"}, {"env": "eks"}), "eks")
        self.assertEqual(policy_errors(manifest("HorizontalPodAutoscaler", {}), "eks"), [])
        self.assertEqual(policy_errors(manifest("Pod", {"containers": [{"resources": {"requests": {"cpu": "100m"}}}]}), "eks"), [])

    def test_both_low_reservation_platforms_are_detected(self):
        for platform in ("k3s", "orb"):
            with self.subTest(platform=platform):
                self.assertEqual(target_platform({"appset": f"apps/{platform}/example.yaml"}, {}), platform)
                self.assertEqual(target_platform({"appset": "apps/example.yaml"}, {"env": platform}), platform)

    def test_main_init_and_sidecar_container_resources_are_rejected(self):
        for platform in ("k3s", "orb"):
            for container_key in ("containers", "initContainers", "ephemeralContainers"):
                for field in ("requests", "limits"):
                    with self.subTest(platform=platform, containers=container_key, field=field):
                        spec = {"template": {"spec": {container_key: [{"name": "sidecar", "resources": {field: {"memory": "128Mi"}}}]}}}
                        errors = policy_errors(manifest("Job", spec), platform)
                        self.assertEqual(len(errors), 1)
                        self.assertIn(field, errors[0])

    def test_pvc_storage_and_empty_compute_settings_are_allowed(self):
        pvc = manifest("PersistentVolumeClaim", {"resources": {"requests": {"storage": "5Gi"}}})
        pod = manifest("Pod", {"containers": [{"resources": None}, {"resources": {}}, {}], "initContainers": None})
        for platform in ("k3s", "orb"):
            self.assertEqual(policy_errors(pvc + "\n---\n" + pod, platform), [])

    def test_all_autoscaler_kinds_are_rejected(self):
        for kind in ("HorizontalPodAutoscaler", "VerticalPodAutoscaler", "ScaledObject", "ScaledJob"):
            for platform in ("k3s", "orb"):
                with self.subTest(kind=kind, platform=platform):
                    self.assertEqual(len(policy_errors(manifest(kind, {}), platform)), 1)

    def test_helmchartconfig_cannot_reenable_traefik_defaults(self):
        valid = manifest("HelmChartConfig", {"valuesContent": "resources: null\nautoscaling:\n  enabled: false\n"}, "traefik")
        missing = manifest("HelmChartConfig", {"valuesContent": "providers: {}"}, "traefik")
        for platform in ("k3s", "orb"):
            self.assertEqual(policy_errors(valid, platform), [])
            self.assertEqual(len(policy_errors(missing, platform)), 2)

    def test_operator_defaults_and_reloader_resources_are_checked(self):
        for kind in ("VMAgent", "VMAlert", "VMAlertmanager", "VMSingle"):
            with self.subTest(kind=kind):
                self.assertTrue(policy_errors(manifest(kind, {}), "k3s"))
                self.assertEqual(policy_errors(manifest(kind, {"useDefaultResources": False}), "k3s"), [])
        reloader = {"useDefaultResources": False, "configReloaderResources": {"limits": {"cpu": "100m"}}}
        self.assertIn("configReloaderResources", policy_errors(manifest("VMAgent", reloader), "k3s")[0])

    def test_vmcluster_policy_is_checked_per_component(self):
        valid = {name: {"useDefaultResources": False} for name in ("vminsert", "vmselect", "vmstorage")}
        self.assertEqual(policy_errors(manifest("VMCluster", valid), "k3s"), [])
        valid["vmselect"] = {"replicaCount": 1}
        self.assertIn("vmselect", policy_errors(manifest("VMCluster", valid), "k3s")[0])
        valid["vmselect"] = {}
        self.assertIn("vmselect", policy_errors(manifest("VMCluster", valid), "k3s")[0])

    def test_crd_schemas_are_not_treated_as_workloads(self):
        schema = {"versions": [{"schema": {"default": {"resources": {"requests": {"cpu": "100m"}}}}}]}
        self.assertEqual(policy_errors(manifest("CustomResourceDefinition", schema), "k3s"), [])


if __name__ == "__main__":
    unittest.main()

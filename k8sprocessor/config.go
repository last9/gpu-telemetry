// Copyright (c) Last9, Inc.
// All rights reserved.
package k8sprocessor

import k8shelper "github.com/last9/gpu-telemetry/k8shelper"

// Config is the configuration for the k8s processor.
// It embeds k8shelper.Config so all K8s connection settings are unified.
type Config = k8shelper.Config

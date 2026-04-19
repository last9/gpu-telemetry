// Copyright (c) Last9, Inc.
// All rights reserved.
package k8sprocessor

import (
	"context"
	"log"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/ptrace"

	k8shelper "github.com/last9/gpu-telemetry/k8shelper"
)

type k8sInfoTraces struct {
	next consumer.Traces
	K8sProcessorBase
}

func newK8sInfoTraces(next consumer.Traces, cfg component.Config) *k8sInfoTraces {
	return &k8sInfoTraces{
		next:             next,
		K8sProcessorBase: NewK8sProcessorBase(cfg),
	}
}

func (kt *k8sInfoTraces) processTraces(ctx context.Context, traces ptrace.Traces) (ptrace.Traces, error) {
	gpu2k8s, err := k8shelper.GetGPU2K8s(kt.Config)
	if err != nil {
		log.Println("k8sprocessor: error getting GPU-to-K8s mapping:", err)
		gpu2k8s = make(map[string]k8shelper.K8sMetadata)
	}

	cloudZone, cloudRegion := extractCloudInfo(gpu2k8s)

	resourceSpansSlice := traces.ResourceSpans()
	for i := 0; i < resourceSpansSlice.Len(); i++ {
		kt.AddCloudAttrs(resourceSpansSlice.At(i).Resource().Attributes(), cloudZone, cloudRegion)
		// Resource-level aggregation: attach all pod names on this node
		kt.AddK8sMetadataSlice(
			resourceSpansSlice.At(i).Resource().Attributes(),
			k8shelper.GetGPUData(gpu2k8s),
		)

		scopeSpansSlice := resourceSpansSlice.At(i).ScopeSpans()
		for j := 0; j < scopeSpansSlice.Len(); j++ {
			spansSlice := scopeSpansSlice.At(j).Spans()
			for k := 0; k < spansSlice.Len(); k++ {
				span := spansSlice.At(k)
				gpuVal, hasGPU := span.Attributes().Get(gpuIndex)
				if hasGPU {
					if meta, ok := gpu2k8s[gpuVal.Str()]; ok {
						kt.AddK8sMetadata(span.Attributes(), meta)
					}
				}
			}
		}
	}

	return traces, nil
}

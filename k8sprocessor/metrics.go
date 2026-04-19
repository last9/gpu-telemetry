// Copyright (c) Last9, Inc.
// All rights reserved.
package k8sprocessor

import (
	"context"
	"log"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/pmetric"

	k8shelper "github.com/last9/gpu-telemetry/k8shelper"
)

type k8sInfoMetrics struct {
	next consumer.Metrics
	K8sProcessorBase
}

func newK8sInfoMetrics(next consumer.Metrics, cfg component.Config) *k8sInfoMetrics {
	return &k8sInfoMetrics{
		next:             next,
		K8sProcessorBase: NewK8sProcessorBase(cfg),
	}
}

func (km *k8sInfoMetrics) processMetrics(ctx context.Context, metrics pmetric.Metrics) (pmetric.Metrics, error) {
	gpu2k8s, err := k8shelper.GetGPU2K8s(km.Config)
	if err != nil {
		log.Println("k8sprocessor: error getting GPU-to-K8s mapping:", err)
		gpu2k8s = make(map[string]k8shelper.K8sMetadata)
	}

	cloudZone, cloudRegion := extractCloudInfo(gpu2k8s)

	resourceMetricsSlice := metrics.ResourceMetrics()
	for i := range resourceMetricsSlice.Len() {
		km.AddCloudAttrs(resourceMetricsSlice.At(i).Resource().Attributes(), cloudZone, cloudRegion)
		scopeMetricsSlice := resourceMetricsSlice.At(i).ScopeMetrics()
		for j := range scopeMetricsSlice.Len() {
			metricsSlice := scopeMetricsSlice.At(j).Metrics()
			for k := range metricsSlice.Len() {
				metric := metricsSlice.At(k)
				switch metric.Type() {
				case pmetric.MetricTypeGauge:
					km.enrichNumberDataPoints(metric.Gauge().DataPoints(), gpu2k8s)
				case pmetric.MetricTypeSum:
					km.enrichNumberDataPoints(metric.Sum().DataPoints(), gpu2k8s)
				case pmetric.MetricTypeHistogram:
					datapoints := metric.Histogram().DataPoints()
					for l := range datapoints.Len() {
						km.enrichAttrMap(datapoints.At(l).Attributes(), gpu2k8s)
					}
				case pmetric.MetricTypeExponentialHistogram:
					datapoints := metric.ExponentialHistogram().DataPoints()
					for l := range datapoints.Len() {
						km.enrichAttrMap(datapoints.At(l).Attributes(), gpu2k8s)
					}
				case pmetric.MetricTypeSummary:
					datapoints := metric.Summary().DataPoints()
					for l := range datapoints.Len() {
						km.enrichAttrMap(datapoints.At(l).Attributes(), gpu2k8s)
					}
				}
			}
		}
	}

	return metrics, nil
}

func (km *k8sInfoMetrics) enrichNumberDataPoints(datapoints pmetric.NumberDataPointSlice, gpu2k8s map[string]k8shelper.K8sMetadata) {
	for l := range datapoints.Len() {
		attrs := datapoints.At(l).Attributes()
		km.enrichAttrMap(attrs, gpu2k8s)
	}
}

func (km *k8sInfoMetrics) enrichAttrMap(attrs pcommon.Map, gpu2k8s map[string]k8shelper.K8sMetadata) {
	gpuVal, hasGPU := attrs.Get(gpuIndex)
	if hasGPU {
		gpuIdx := gpuVal.Str()
		if meta, ok := gpu2k8s[gpuIdx]; ok {
			km.AddK8sMetadata(attrs, meta)
		}
	} else {
		// Host-level metric: attach aggregated metadata for all pods on node
		km.AddK8sMetadataSlice(attrs, k8shelper.GetGPUData(gpu2k8s))
	}
}

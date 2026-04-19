// Copyright (c) Last9, Inc.
// All rights reserved.
package k8sprocessor

import (
	"context"
	"log"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/processor"
	"go.opentelemetry.io/collector/processor/processorhelper"

	k8shelper "github.com/last9/gpu-telemetry/k8shelper"
)

const (
	// typeStr is the "type" key used in the OTel collector configuration.
	typeStr = "k8s"
)

// NewFactory creates a factory for the k8s attribution processor.
func NewFactory() processor.Factory {
	return processor.NewFactory(
		component.MustNewType(typeStr),
		createDefaultConfig,
		processor.WithTraces(createTracesProcessor, component.StabilityLevelAlpha),
		processor.WithMetrics(createMetricsProcessor, component.StabilityLevelAlpha),
		processor.WithLogs(createLogsProcessor, component.StabilityLevelAlpha),
	)
}

func createDefaultConfig() component.Config {
	return &k8shelper.Config{
		NodeName:       "", // populated from MY_NODE_NAME env var at runtime
		KubeconfigPath: "", // empty → in-cluster config
		CacheDuration:  60,
	}
}

func createTracesProcessor(
	ctx context.Context,
	set processor.Settings,
	cfg component.Config,
	nextTracesConsumer consumer.Traces,
) (processor.Traces, error) {
	log.Println("Creating K8s Trace Processor")
	kt := newK8sInfoTraces(nextTracesConsumer, cfg)
	return processorhelper.NewTraces(
		ctx, set, cfg, nextTracesConsumer, kt.processTraces,
		processorhelper.WithCapabilities(kt.Capabilities()),
		processorhelper.WithStart(kt.Start),
		processorhelper.WithShutdown(kt.Shutdown),
	)
}

func createMetricsProcessor(
	ctx context.Context,
	set processor.Settings,
	cfg component.Config,
	nextMetricsConsumer consumer.Metrics,
) (processor.Metrics, error) {
	log.Println("Creating K8s Metrics Processor")
	km := newK8sInfoMetrics(nextMetricsConsumer, cfg)
	return processorhelper.NewMetrics(
		ctx, set, cfg, nextMetricsConsumer, km.processMetrics,
		processorhelper.WithCapabilities(km.Capabilities()),
		processorhelper.WithStart(km.Start),
		processorhelper.WithShutdown(km.Shutdown),
	)
}

func createLogsProcessor(
	ctx context.Context,
	set processor.Settings,
	cfg component.Config,
	nextLogsConsumer consumer.Logs,
) (processor.Logs, error) {
	log.Println("Creating K8s Logs Processor")
	kl := newK8sInfoLogs(nextLogsConsumer, cfg)
	return processorhelper.NewLogs(
		ctx, set, cfg, nextLogsConsumer, kl.processLogs,
		processorhelper.WithCapabilities(kl.Capabilities()),
		processorhelper.WithStart(kl.Start),
		processorhelper.WithShutdown(kl.Shutdown),
	)
}

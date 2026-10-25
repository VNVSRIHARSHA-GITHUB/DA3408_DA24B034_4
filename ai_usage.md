# AI Usage Disclosure

## AI Tool Used

- Claude

## How It Was Used and Impact

1. **Conceptual Clarification**
   - Used AI to understand Prometheus, node_exporter, Alertmanager, Grafana, the four Prometheus metric types (Counter, Gauge, Histogram, Summary) and PromQL functions such as `rate()`, `increase()` and `histogram_quantile()`.
   - **Impact:** Helped me understand how the monitoring pipeline fits together and how to read and verify the metrics.

2. **Code and Configuration Generation**
   - some part of PromQL generated with AI is attributed with the prompts used in [`Ai_prompt_usage.md`](Ai_prompt_usage.md), as required .
   - **Impact:** Sped up the process , so more time went into testing, collecting evidence and verifying the metrics.

3. **Debugging and Troubleshooting**
   - Used AI to diagnose issues found while running the system, for example the repetition bug in captions ("a gi gi gi …") for a giraffe image, a Docker container name conflict and dashboard layout problems.
   - **Impact:** Helped identify the causes and apply fixes.

4. **Command and Documentation Assistance**
   - Used AI to understand the terminal commands used and assisted in structuring the README.md(I verified the README.md).
   - **Impact:** Helped with running the stack correctly and documenting the work clearly.

## Responsibility

- I reviewed, executed and understood the code, configuration and commands used in the final submission.
- The app, the monitoring stack and the alerts were actually run on my laptop. All screenshots, the metric snapshot and the measured numbers (latency, CPU, memory) come from real runs, not generated or fabricated by AI.
- I verified the hand calculations in METRICS.md against the values shown by Prometheus and Grafana.

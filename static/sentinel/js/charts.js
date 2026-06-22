(function () {
    function buildBandsPlugin() {
        return {
            id: "sentinelBands",
            beforeDraw(chart) {
                const { ctx, chartArea, scales } = chart;
                if (!chartArea || !scales.y) {
                    return;
                }
                const { left, right } = chartArea;
                const yClear = scales.y.getPixelForValue(0.25);
                const yBlock = scales.y.getPixelForValue(0.72);
                ctx.save();
                ctx.fillStyle = "rgba(20, 184, 166, 0.08)";
                ctx.fillRect(left, yClear, right - left, chartArea.bottom - yClear);
                ctx.fillStyle = "rgba(245, 158, 11, 0.08)";
                ctx.fillRect(left, yBlock, right - left, yClear - yBlock);
                ctx.fillStyle = "rgba(239, 68, 68, 0.08)";
                ctx.fillRect(left, chartArea.top, right - left, yBlock - chartArea.top);
                ctx.restore();
            }
        };
    }

    function initChart() {
        const canvas = document.getElementById("scoreTimeline");
        if (!canvas || !window.Chart) {
            return null;
        }
        const seed = window.SENTINEL_CHART_BOOT || { labels: [], points: [] };
        return new Chart(canvas, {
            type: "line",
            data: {
                labels: seed.labels,
                datasets: [
                    {
                        label: "Live Suspicion Score",
                        data: seed.points,
                        borderColor: "#7c3aed",
                        backgroundColor: "rgba(124, 58, 237, 0.18)",
                        fill: true,
                        tension: 0.35,
                    },
                    {
                        label: "τ_clear",
                        data: seed.labels.map(() => 0.25),
                        borderColor: "#14b8a6",
                        borderDash: [6, 6],
                        pointRadius: 0,
                    },
                    {
                        label: "τ_block",
                        data: seed.labels.map(() => 0.72),
                        borderColor: "#ef4444",
                        borderDash: [6, 6],
                        pointRadius: 0,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        ticks: { color: "#94a3b8" },
                        grid: { color: "rgba(148, 163, 184, 0.08)" }
                    },
                    y: {
                        min: 0,
                        max: 1,
                        ticks: { color: "#94a3b8" },
                        grid: { color: "rgba(148, 163, 184, 0.08)" }
                    }
                },
                plugins: {
                    legend: {
                        labels: { color: "#e2e8f0" }
                    }
                }
            },
            plugins: [buildBandsPlugin()]
        });
    }

    function fallbackPoll() {
        fetch("/api/v1/dashboard-state/")
            .then((response) => response.json())
            .then((payload) => {
                const sensorsNode = document.getElementById("sensor-grid-body");
                if (sensorsNode && window.htmx) {
                    htmx.trigger(sensorsNode, "refresh");
                }
                return payload;
            })
            .catch(() => null);
    }

    document.addEventListener("DOMContentLoaded", function () {
        const chart = initChart();
        let chartCursor = 0;
        let ws;
        try {
            const protocol = window.location.protocol === "https:" ? "wss" : "ws";
            ws = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard/`);
            ws.onmessage = function (event) {
                const payload = JSON.parse(event.data);
                if (payload.event === "score_update" && chart) {
                    chart.data.labels.push(`C${++chartCursor}`);
                    chart.data.datasets[0].data.push(payload.data.score || 0);
                    if (chart.data.labels.length > 50) {
                        chart.data.labels.shift();
                        chart.data.datasets[0].data.shift();
                    }
                    chart.update("none");
                }
                if (payload.event === "alert") {
                    const stack = document.getElementById("toast-stack");
                    if (stack) {
                        const toast = document.createElement("div");
                        toast.className = "rounded-2xl border border-red-500/30 bg-[#1a1d26] px-4 py-3 text-sm text-slate-100 shadow-2xl";
                        toast.textContent = payload.data.message;
                        stack.prepend(toast);
                        setTimeout(() => toast.remove(), 6000);
                    }
                }
            };
            ws.onerror = fallbackPoll;
        } catch (error) {
            fallbackPoll();
        }
        document.body.addEventListener("htmx:afterRequest", function (event) {
            if (event.target.id === "command-result") {
                const scoreText = event.target.textContent.match(/score=([0-9.]+)/);
                if (scoreText) {
                    window.dispatchEvent(new CustomEvent("sentinel-score", { detail: { score: Number(scoreText[1]) } }));
                }
            }
        });
        if (!ws) {
            setInterval(fallbackPoll, 5000);
        }
    });
})();

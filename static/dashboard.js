/*
 * ダッシュボード用 JavaScript
 * ============================================
 * Chart.js で棒グラフ2本を描画する。
 *
 * データは Python が dashboard.html に埋め込んだ
 * <script type="application/json" id="..."> から読み取る。
 * これにより、この JS ファイルにはテンプレート記法を一切書かずに済む。
 */

// データアイランドから集計結果を取り出す（[{label, count}, ...] の形）
const categoryData = JSON.parse(
    document.getElementById("category-data").textContent
);
const locationData = JSON.parse(
    document.getElementById("location-data").textContent
);

// グラフ共通オプション（縦軸を整数刻みに、凡例は1系列だけだから非表示）
const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
        y: {
            beginAtZero: true,
            ticks: { stepSize: 1, precision: 0 },
        },
    },
    plugins: {
        legend: { display: false },
        tooltip: {
            callbacks: {
                label: (ctx) => `${ctx.parsed.y} 商品`,
            },
        },
    },
};

// カテゴリ別 棒グラフ（青系）
new Chart(document.getElementById("categoryChart"), {
    type: "bar",
    data: {
        labels: categoryData.map((d) => d.label),
        datasets: [
            {
                label: "商品数",
                data: categoryData.map((d) => d.count),
                backgroundColor: "rgba(54, 162, 235, 0.7)",
                borderColor: "rgba(54, 162, 235, 1)",
                borderWidth: 1,
            },
        ],
    },
    options: commonOptions,
});

// 保管場所別 棒グラフ（オレンジ系）
new Chart(document.getElementById("locationChart"), {
    type: "bar",
    data: {
        labels: locationData.map((d) => d.label),
        datasets: [
            {
                label: "商品数",
                data: locationData.map((d) => d.count),
                backgroundColor: "rgba(255, 159, 64, 0.7)",
                borderColor: "rgba(255, 159, 64, 1)",
                borderWidth: 1,
            },
        ],
    },
    options: commonOptions,
});

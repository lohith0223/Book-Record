document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.alert').forEach((alert) => {
    window.setTimeout(() => bootstrap.Alert.getOrCreateInstance(alert).close(), 4500);
  });
  if (window.Chart && window.mbaCharts) {
    const common = {responsive: true, maintainAspectRatio: false, plugins: {legend: {display: false}}, scales: {y: {beginAtZero: true, grid: {color: '#edf1ef'}, ticks: {precision: 0}}, x: {grid: {display: false}}}};
    const floorCanvas = document.getElementById('floorChart');
    if (floorCanvas) new Chart(floorCanvas, {type: 'bar', data: {labels: window.mbaCharts.floorLabels.map((floor) => `Floor ${floor}`), datasets: [{data: window.mbaCharts.floorValues, backgroundColor: ['#137c74', '#d88a2b'], borderRadius: 5, barThickness: 28}]}, options: common});
    const standCanvas = document.getElementById('standChart');
    if (standCanvas) new Chart(standCanvas, {type: 'bar', data: {labels: window.mbaCharts.standLabels, datasets: [{data: window.mbaCharts.standValues, backgroundColor: '#5baea2', borderRadius: 4, barThickness: 18}]}, options: {...common, indexAxis: 'y'}});
  }
});
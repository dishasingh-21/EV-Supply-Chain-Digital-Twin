const fs = require("fs");
const stations = require("./CoordinateData/data.js");

function haversine(a, b) {
    const R = 6371;
    let lat1 = a.lat * Math.PI / 180;
    let lat2 = b.lat * Math.PI / 180;
    let lon1 = a.lon * Math.PI / 180;
    let lon2 = b.lon * Math.PI / 180;
    let Dlat = lat2 - lat1;
    let Dlon = lon2 - lon1;
    let h = Math.sin(Dlat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * (Math.sin(Dlon / 2) ** 2);
    let ans = R * (2 * Math.asin(Math.sqrt(h)));
    return ans;
}

async function precomputeAdjacencyKeys() {
    let station = [...stations];
    let distances = {};
    for (let i = 0; i < station.length; i++) {
        for (let j = i + 1; j < station.length; j++) {
            let d = haversine(station[i], station[j]);
            if (d <= 400) distances[`${i}-${j}`] = d;
        }
    }
    let graph = {
        station, distances, stats: { pairs: Object.keys(distances).length }
    }
    fs.writeFileSync("workable_stations.json", JSON.stringify(graph, null, 2));
}
precomputeAdjacencyKeys();
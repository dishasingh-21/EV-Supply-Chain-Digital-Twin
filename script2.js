console.log("SCRIPT LOADED");

const params = new URLSearchParams(window.location.search);
const start = params.get("start");
const end = params.get("end");
const batteryPercent = parseFloat(params.get("battery"));

const DEBUG_VISUAL = true;
//Debugging and visualisation
let debug_layers = [];
function sleep(ms) {
    return new Promise(res => setTimeout(res, ms));
}

function clear_layer() {
    debug_layers.forEach(layer => map.removeLayer(layer));
    debug_layers = [];
}

function drawDebugEdge(a, b, color) {
    if (!DEBUG_VISUAL) return;
    let line = L.polyline([
        [a.lat, a.lon], [b.lat, b.lon]
    ], {
        color: color,
        weight: 3,
        opacity: 0.6
    }).addTo(map);
    debug_layers.push(line);
}


//Leaflet.js part
var map = L.map('map').setView([26.5, 74.5], 6);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

//Distance calculation between two points (Local Optimization using Open Source Routing Machine)
async function distance(a, b) {
    let url = `https://router.project-osrm.org/route/v1/driving/${a.lon},${a.lat};${b.lon},${b.lat}?overview=false`;
    let res = await fetch(url);
    let data = await res.json();
    return data.routes[0].distance / 1000;
}

//Haversine distance.
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

//Getting coordinates of locations
async function getCoordinates(place) {
    try {
        let res = await fetch(
            `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(place)}&format=json&addressdetails=1&limit=1`
        );
        let data = await res.json();
        if (data.length === 0) return null;
        return {
            name: place,
            lat: parseFloat(data[0].lat),
            lon: parseFloat(data[0].lon)
        };
    }
    catch (error) {
        console.error("Geocoding error:", error);
        return null;
    }
}

//Priority Queue Implementation
class PriorityQueue {
    constructor() {
        this.heap = [];
    }
    getLeftChildIndex(parentIndex) {
        return 2 * parentIndex + 1;
    }
    getRightChildIndex(parentIndex) {
        return 2 * parentIndex + 2;
    }
    getParentIndex(childIndex) {
        return Math.floor((childIndex - 1) / 2);
    }
    hasLeftChild(index) {
        return this.getLeftChildIndex(index) < this.heap.length;
    }
    hasRightChild(index) {
        return this.getRightChildIndex(index) < this.heap.length;
    }
    hasParent(index) {
        return this.getParentIndex(index) >= 0;
    }
    leftChild(index) {
        return this.heap[this.getLeftChildIndex(index)];
    }
    rightChild(index) {
        return this.heap[this.getRightChildIndex(index)];
    }
    parent(index) {
        return this.heap[this.getParentIndex(index)];
    }
    swap(idx1, idx2) {
        const temp = this.heap[idx1];
        this.heap[idx1] = this.heap[idx2];
        this.heap[idx2] = temp;
    }
    isEmpty() {
        if (this.heap.length === 0) return true;
        return false;
    }
    top() {
        if (this.heap.length === 0) return null;
        return this.heap[0];
    }
    remove() {
        if (this.heap.length === 0) return null;
        const item = this.heap[0];
        this.heap[0] = this.heap[this.heap.length - 1];
        this.heap.pop();
        this.heapifyDown();
        return item;
    }
    add(item) {
        this.heap.push(item);
        this.heapifyUp();
    }
    heapifyUp() {
        let index = this.heap.length - 1;
        while (this.hasParent(index) && this.parent(index).f > this.heap[index].f) {
            this.swap(this.getParentIndex(index), index);
            index = this.getParentIndex(index);
        }
    }
    heapifyDown() {
        let index = 0;
        while (this.hasLeftChild(index)) {
            let smallerChildIndex = this.getLeftChildIndex(index);
            if (this.hasRightChild(index) && this.rightChild(index).f < this.leftChild(index).f) {
                smallerChildIndex = this.getRightChildIndex(index);
            }
            if (this.heap[index].f > this.heap[smallerChildIndex].f) {
                this.swap(smallerChildIndex, index);
                index = smallerChildIndex;
            } else {
                break;
            }
        }
    }
}

//Caching.
let cache = new Map();
async function getDistance(a, b) {
    let key = `${a.lat},${a.lon}-${b.lat},${b.lon}`;
    let reverseKey = `${b.lat},${b.lon}-${a.lat},${a.lon}`;
    if (cache.has(reverseKey)) return cache.get(reverseKey);
    if (cache.has(key)) return cache.get(key);
    let d = await distance(a, b);
    cache.set(key, d);
    cache.set(reverseKey, d);
    return d;
}

//Route Optimization Core
//1. Checking if we can directly reach destination in one go.
const MAX_RANGE = 400;
async function DirectPossible(START, END, initialRange) {
    let d = await getDistance(START, END);
    let result = d <= initialRange;
    return result;
}

//2. Else we go with A_Star Algorithm.
async function aStar(nodes, start, end, MAX_RANGE, initialRange, adj) {
    let n = nodes.length;
    let g = new Array(n).fill(Infinity);
    let f = new Array(n).fill(Infinity);
    let parent = new Array(n).fill(null);
    let bestBattery = new Array(n).fill(0);
    let visited = new Set();

    let open = new PriorityQueue();
    g[start] = 0;
    f[start] = haversine(nodes[start], nodes[end]);
    bestBattery[start] = initialRange;
    open.add({ idx: start, f: f[start], battery: initialRange });
    let iterations = 0;
    while (!open.isEmpty()) {
        let { idx: current, battery } = open.remove();
        let visitKey = `${current}-${Math.floor(battery / 25)}`;
        if (visited.has(visitKey)) continue;
        visited.add(visitKey);

        if (current === end) {
            console.log("Destination reached in A* after", iterations, "iterations");
            break;
        }
        iterations++;
        if (iterations > 20000) {
            console.warn("A* exceeded iteration limit.");
            return null;
        }

        let neighbors = adj[current];
        for (let i = 0; i < neighbors.length; i++) {
            let neighborIdx = neighbors[i].node;
            let d = neighbors[i].dist;

            if (d > battery) continue;

            let isEndNode = neighborIdx === end;
            let newBattery = isEndNode ? (battery - d) : MAX_RANGE;

            let new_g = g[current] + d;
            if (new_g >= g[neighborIdx]) continue;

            g[neighborIdx] = new_g;
            bestBattery[neighborIdx] = newBattery;

            let h = haversine(nodes[neighborIdx], nodes[end]);
            f[neighborIdx] = g[neighborIdx] + h;

            parent[neighborIdx] = {
                node: current,
                battery: battery
            };
            open.add({ idx: neighborIdx, f: f[neighborIdx], battery: newBattery });
        }
    }
    let path = [];
    let cursor = end;
    let current_battery = bestBattery[end];
    let seen = new Set();
    while (cursor !== null && cursor !== start) {
        if (seen.has(cursor)) {
            console.error("Cycle detected in graph path reconstruction!");
            return null;
        }
        seen.add(cursor);
        path.push(nodes[cursor]);
        if (parent[cursor]) {
            current_battery = parent[cursor].battery;
            cursor = parent[cursor].node;
        }
        else {
            console.log("Path broken at cursor:", cursor);
            return null;
        }
    }
    if (cursor === start) path.push(nodes[start]);
    path.reverse();
    return path;
}

//Draw Route.
async function drawRoute(route, batteryPercent) {
    let remaining = MAX_RANGE * (batteryPercent / 100);
    let fullPath = [];
    let promises = [];
    let actualTotalDistance = 0;

    for (let i = 0; i < route.length - 1; i++) {
        let start = route[i];
        let end = route[i + 1];
        let url = `https://router.project-osrm.org/route/v1/driving/${start.lon},${start.lat};${end.lon},${end.lat}?overview=full&geometries=geojson`;
        promises.push(fetch(url).then(res => res.json()));
    }

    let results = await Promise.all(promises);
    results.forEach((data, i) => {
        if (!data.routes || data.routes.length === 0) return;
        let distance_travelled = data.routes[0].distance / 1000;
        actualTotalDistance += distance_travelled;

        let battery_at_arrival = remaining - distance_travelled;
        let next = route[i + 1];

        let coords = data.routes[0].geometry.coordinates;
        coords.forEach((c) => {
            const pt = [c[1], c[0]];
            if (fullPath.length > 0) {
                const last = fullPath[fullPath.length - 1];
                if (last[0] === pt[0] && last[1] === pt[1]) {
                    return;
                }
            }
            fullPath.push(pt);
        });
        let midcoords = coords[Math.floor(coords.length / 2)];
        let mid = [midcoords[1], midcoords[0]];
        L.marker(mid).addTo(map).bindPopup(
            `Distance: ${distance_travelled.toFixed(1)} km<br>
            Battery on arrival: ${Math.max(0, battery_at_arrival).toFixed(1)} km`
        );

        remaining = battery_at_arrival;
        if (next.isCharging) {
            remaining = MAX_RANGE;
        }
    });

    let poly = L.polyline(fullPath, {
        color: 'black',
        weight: 6
    }).addTo(map);
    map.fitBounds(poly.getBounds());

    route.forEach((p, index) => {
        let isStart = index === 0;
        let isEnd = index === route.length - 1;
        let isCharging = p.isCharging;
        let color = "blue";
        if (isStart) color = "green";
        else if (isEnd) color = "red";
        else if (isCharging) color = "orange";
        let icon = L.circleMarker([p.lat, p.lon], {
            radius: 8,
            color: color,
            fillColor: color,
            fillOpacity: 1
        }).addTo(map);
        icon.bindPopup(
            `${p.name || p.subtown || "Charging Station"}`
        );
        let label = p.name || p.subtown || p.town || "Charging Station";
        if (isCharging) {
            icon.bindTooltip(label, {
                permanent: true,
                direction: "top",
                offset: [0, -10],
                className: "station-label"
            });
        }
    });

    return actualTotalDistance;
}

//get total distance.
function getTotalDistance(route) {
    let total = 0;
    for (let i = 0; i < route.length - 1; i++) {
        let dist = haversine(route[i], route[i + 1]);
        total += dist;
    }
    return total;
}

function updateStatus(text, color = "var(--primary)") {
    const statusText = document.getElementById("status-text");
    const statusDot = document.getElementById("status-dot");
    if (statusText) statusText.innerText = text;
    if (statusDot) statusDot.style.background = color;
}

//starter function.
async function init() {
    console.log("INIT RUNNING");
    updateStatus("Loading Graph Data...", "var(--accent)");

    try {
        const response = await fetch('workable_stations.json');
        graph = await response.json();
        console.log("Graph loaded:", graph.stats);

        // Pre-process adjacency list for stations (one-time)
        graph.stationAdj = new Array(graph.station.length).fill(0).map(() => []);
        for (let key in graph.distances) {
            let parts = key.split('-');
            let u = parseInt(parts[0]);
            let v = parseInt(parts[1]);
            let d = graph.distances[key];
            if (u < graph.station.length && v < graph.station.length) {
                graph.stationAdj[u].push({ node: v, dist: d });
                graph.stationAdj[v].push({ node: u, dist: d });
            }
        }
    } catch (error) {
        console.error("Failed to load stations:", error);
        alert("Please ensure workable_stations.json is available");
        return;
    }

    updateStatus("Geocoding Locations...", "var(--accent)");
    let startloc = await getCoordinates(start);
    let endloc = await getCoordinates(end);
    if (!startloc || !endloc) {
        updateStatus("Geocoding Failed", "var(--danger)");
        alert(`Could not find coordinates for ${!startloc ? start : end}. Please try a more specific name.`);
        return;
    }

    let initialRange = MAX_RANGE * (batteryPercent / 100);
    console.log(`Target: ${start} to ${end}. Initial range: ${initialRange.toFixed(1)} km`);

    let route;
    let directPossible = false;
    try {
        directPossible = await DirectPossible(startloc, endloc, initialRange);
    } catch (e) {
        console.log("Direct check failed or too far for OSRM, falling back to A*.");
    }

    if (directPossible) {
        updateStatus("Direct Route Found", "var(--success)");
        console.log("Direct route possible!");
        route = [startloc, endloc];
    }
    else {
        updateStatus("Optimizing Route Path...", "var(--accent)");
        console.log("Calculating route with charging stops...");
        let stationsList = graph.station.map(s => ({ ...s, isCharging: true }));
        let AllNodes = [startloc, ...stationsList, endloc];
        let n = AllNodes.length;
        let startIdx = 0;
        let endIdx = n - 1;
        let adj = new Array(n).fill(0).map(() => []);

        // 1. Neighbors of startloc (index 0)
        for (let j = 0; j < stationsList.length; j++) {
            let d = haversine(startloc, stationsList[j]);
            if (d <= initialRange) {
                adj[0].push({ node: j + 1, dist: d });
            }
        }

        // 2. Neighbors between stations (indices 1 to n-2)
        for (let i = 0; i < stationsList.length; i++) {
            let currentAllNodesIdx = i + 1;
            let stationNeighbors = graph.stationAdj[i];
            for (let neighbor of stationNeighbors) {
                adj[currentAllNodesIdx].push({
                    node: neighbor.node + 1,
                    dist: neighbor.dist
                });
            }

            // Also check if this station can reach endloc
            let dToEnd = haversine(stationsList[i], endloc);
            if (dToEnd <= MAX_RANGE) {
                adj[currentAllNodesIdx].push({
                    node: endIdx,
                    dist: dToEnd
                });
            }
        }

        route = await aStar(AllNodes, startIdx, endIdx, MAX_RANGE, initialRange, adj);
    }

    if (!route || route.length < 2) {
        alert("No feasible route found within battery constraints.");
        console.log("No route found between", startloc, "and", endloc);
        return;
    }
    updateStatus("Drawing Path...", "var(--accent)");
    let actualDistance = await drawRoute(route, batteryPercent);

    // Update UI Stats with actual road distance if available
    if (actualDistance > 0) {
        document.getElementById("distance").innerText = actualDistance.toFixed(1);

        // Re-calculate ETA with actual road distance
        let actualHours = actualDistance / 60;
        let chargeStops = route.filter(p => p.isCharging).length;
        let actualTotalMinutes = (actualHours * 60) + (chargeStops * 30);
        let actualEstHours = Math.floor(actualTotalMinutes / 60);
        let actualEstMins = Math.round(actualTotalMinutes % 60);

        document.getElementById("eta").innerText = `${actualEstHours}h ${actualEstMins}m`;
        const actualTotalEtaElem = document.getElementById("total-eta");
        if (actualTotalEtaElem) actualTotalEtaElem.innerText = `${actualEstHours.toString().padStart(2, '0')}:${actualEstMins.toString().padStart(2, '0')} hrs`;
    }

    updateStatus("Route Optimized", "var(--success)");
    console.log("Route:", route);
}


init();
"use client";

import * as React from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { FeatureCollection } from "@/lib/types";

export interface LayerVis {
  flood: boolean;
  landslide: boolean;
  coastal: boolean;
  cloudburst: boolean;
  red: boolean;
  yellow: boolean;
  green: boolean;
  infra: boolean;
}

const DEFAULT_VIS: LayerVis = {
  flood: true,
  landslide: false,
  coastal: false,
  cloudburst: true,
  red: true,
  yellow: true,
  green: true,
  infra: true,
};

export function RiskMap({
  habitations,
  destinations = null,
  layerVis = DEFAULT_VIS,
  fitBounds = null,
  onSelectFeatures,
}: {
  habitations: FeatureCollection;
  destinations?: FeatureCollection | null;
  layerVis?: LayerVis;
  /** [[west, south], [east, north]] - animates the camera when it changes. */
  fitBounds?: [[number, number], [number, number]] | null;
  onSelectFeatures: (p: Record<string, unknown> | null) => void;
}) {
  const container = React.useRef<HTMLDivElement | null>(null);
  const mapRef = React.useRef<maplibregl.Map | null>(null);
  const latestRef = React.useRef<{
    vis: LayerVis;
    onSelect: (p: Record<string, unknown> | null) => void;
    habitations: FeatureCollection;
    destinations: FeatureCollection | null;
  }>({
    vis: layerVis,
    onSelect: onSelectFeatures,
    habitations,
    destinations,
  });

  React.useEffect(() => {
    latestRef.current = {
      vis: layerVis,
      onSelect: onSelectFeatures,
      habitations,
      destinations,
    };
  }, [layerVis, onSelectFeatures, habitations, destinations]);

  // one-time map construction + data source & layers
  React.useEffect(() => {
    if (!container.current) return;
    latestRef.current = {
      vis: layerVis,
      onSelect: onSelectFeatures,
      habitations,
      destinations,
    };
    const map = new maplibregl.Map({
      container: container.current!,
      center: [89.5, 27.4],
      zoom: 5.2,
      style: {
        version: 8,
        sources: {
          "carto-dark": {
            type: "raster",
            tiles: ["https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"],
            tileSize: 256,
            attribution: "© CARTO © OSM",
          },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#0b1220" } },
          { id: "carto-dark", type: "raster", source: "carto-dark", minzoom: 0, maxzoom: 20 },
        ],
      },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("load", () => {
      ensureSources(map, latestRef.current.habitations, latestRef.current.destinations);
      applyLayerToggles(map, latestRef.current.vis);
      bindClick(map, () => latestRef.current.onSelect);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // react to prop-driven toggle changes (style may still be loading => skip)
  React.useEffect(() => {
    const map = mapRef.current;
    applyLayerToggles(map!, layerVis);
  }, [layerVis]);

  // push refreshed GeoJSON (e.g. a newly selected district) into the source
  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("habs") as maplibregl.GeoJSONSource | undefined;
    if (src) src.setData(habitations);
  }, [habitations]);

  // district focus animation: fit the selected district's bounding box
  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !fitBounds) return;
    map.fitBounds(fitBounds, { padding: 48, maxZoom: 10, duration: 1400 });
  }, [fitBounds]);

  return <div ref={container} className="h-full w-full rounded-lg" />;
}

function ensureSources(
  map: maplibregl.Map,
  habs: FeatureCollection,
  dests: FeatureCollection | null
) {
  if (!map.getSource("habs")) {
    map.addSource("habs", { type: "geojson", data: habs });
  } else {
    (map.getSource("habs") as maplibregl.GeoJSONSource).setData(habs);
  }
  if (dests && !map.getSource("infra")) {
    map.addSource("infra", { type: "geojson", data: dests });
  }
  // habitation zone layer - high contrast match colour
  map.addLayer({
    id: "habs-zone",
    type: "circle",
    source: "habs",
    paint: {
      "circle-radius": [
        "match",
        ["get", "zone"],
        "red",
        9,
        "yellow",
        7,
        "green",
        6,
        5,
      ],
      "circle-color": [
        "match",
        ["get", "zone"],
        "red",
        "#ef4444",
        "yellow",
        "#facc15",
        "green",
        "#22c55e",
        "#71717a", // unknown/missing/low-confidence -> grey, never hidden
      ],
      "circle-opacity": 0.92,
      "circle-stroke-color": "#0b1220",
      "circle-stroke-width": 1.5,
    },
  });
  map.addLayer({
    id: "habs-label",
    type: "symbol",
    source: "habs",
    layout: {
      "text-field": ["coalesce", ["get", "code"], ""],
      "text-size": 9,
      "text-offset": [0, 1.1],
    },
    paint: { "text-color": "#cbd5e1" },
  });
  if (dests) {
    map.addLayer({
      id: "infra",
      type: "circle",
      source: "infra",
      paint: {
        "circle-radius": 8,
        "circle-color": "#22d3ee",
        "circle-opacity": 0.85,
        "circle-stroke-color": "#0f172a",
        "circle-stroke-width": 2,
      },
    });
  }
}

function bindClick(
  map: maplibregl.Map,
  selectorFn: () => (p: Record<string, unknown> | null) => void
) {
  map.on("click", "habs-zone", (e) => {
    const f = e.features && e.features[0];
    if (!f) return;
    const geom = f.geometry as { type: string; coordinates?: [number, number] };
    if (geom && Array.isArray(geom.coordinates)) {
      map.flyTo({ center: geom.coordinates as [number, number], zoom: 9 });
    }
    selectorFn()(f.properties ?? null);
  });
  map.on("mouseenter", "habs-zone", () => {
    if (map.getCanvas()) map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "habs-zone", () => {
    if (map.getCanvas()) map.getCanvas().style.cursor = "";
  });
}

function applyLayerToggles(map: maplibregl.Map | null, vis: LayerVis) {
  if (!map) return;
  const zonesOn = vis.red || vis.yellow || vis.green;
  for (const [id, state] of Object.entries({
    "habs-zone": zonesOn,
    "habs-label": zonesOn,
    infra: vis.infra,
  } as const)) {
    if (map.getLayer(id)) {
      map.setLayoutProperty(id, "visibility", state ? "visible" : "none");
    }
  }
  // hazard overlay placeholder layer only visible when any hazard toggle open
  if (map.getLayer("haz-heat")) {
    const hazOn = vis.flood || vis.coastal || vis.cloudburst || vis.landslide;
    map.setLayoutProperty("haz-heat", "visibility", hazOn ? "visible" : "none");
  }
}

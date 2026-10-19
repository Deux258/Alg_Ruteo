"""Pruebas reales Playwright. Servidor Docker ya iniciado; Chrome headless."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18081")
    parser.add_argument(
        "--output", type=Path, default=Path("evidencia/local/aereo/interfaz")
    )
    parser.add_argument(
        "--channel", default="chrome", choices=["chrome", "msedge", "chromium"]
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checks = []
    errors = []
    with sync_playwright() as p:
        options = dict(headless=True)
        if args.channel != "chromium":
            options["channel"] = args.channel
        browser = p.chromium.launch(**options)
        try:
            page = browser.new_page(
                viewport={"width": 1440, "height": 1000}, device_scale_factor=1
            )
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "response",
                lambda response: (
                    errors.append(f"Asset {response.status}: {response.url}")
                    if response.status >= 400 and response.url.endswith(".png")
                    else None
                ),
            )
            page.goto(args.url)
            page.wait_for_load_state("networkidle")
            expect(
                page.get_by_role("heading", name="Rutas aéreas para drones", exact=True)
            ).to_be_visible()
            expect(page.locator("#bases option")).to_have_count(6)
            (args.output / "dom_inicial.html").write_text(
                page.content(), encoding="utf-8"
            )
            page.screenshot(path=str(args.output / "inicio.png"), full_page=True)
            hours = page.locator("#weather-hour option").evaluate_all(
                "items => items.filter(e=>e.textContent.includes('admisible')).map(e=>e.value)"
            )
            assert hours, "Sin horas admisibles en la respuesta real"
            page.get_by_label(
                "Horas disponibles del pronóstico", exact=True
            ).select_option(hours[0])
            page.get_by_label(
                "Objetivos de vigilancia de ejemplo", exact=True
            ).select_option("1")

            def calculate():
                with page.expect_response(
                    lambda r: r.url.endswith("/api/aereo/rutas")
                    and r.request.method == "POST"
                ) as response:
                    page.get_by_role(
                        "button", name="Calcular rutas aéreas", exact=True
                    ).click()
                payload = response.value.json()
                expect(page.locator("#result")).not_to_contain_text(
                    "Calculando", timeout=45000
                )
                page.wait_for_function(
                    "!document.querySelector('#map.leaflet-zoom-anim')"
                )
                return payload

            initial = calculate()
            assert initial["status"] == "ready"
            assert len(initial["alternatives"]) >= 2
            expect(page.locator(".alternative")).to_have_count(
                len(initial["alternatives"])
            )
            page.screenshot(path=str(args.output / "rutas.png"), full_page=True)
            checks.append("Misión real con alternativas, retorno y reserva")
            coordinates = initial["alternatives"][0]["outbound"]["coordinates"]
            a, b = max(
                zip(coordinates, coordinates[1:]),
                key=lambda p: (p[1][0] - p[0][0]) ** 2 + (p[1][1] - p[0][1]) ** 2,
            )
            mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
            page.get_by_label("Radio del bloqueo (m)", exact=True).fill("80")
            page.get_by_role("button", name="Bloqueo circular", exact=True).click()
            pixel = page.evaluate(
                "c => {const p=map.latLngToContainerPoint([c[1],c[0]]);return {x:p.x,y:p.y}}",
                mid,
            )
            page.locator("#map").click(position=pixel)
            expect(page.locator("#events-status")).to_contain_text("1 bloqueos")
            blocked = calculate()
            assert blocked["status"] in ["ready", "no_route", "not_feasible"]
            assert blocked["reference"] == initial["reference"]
            assert (
                blocked["alternatives"][0]["outbound"]["edge_ids"]
                != initial["alternatives"][0]["outbound"]["edge_ids"]
            )
            page.screenshot(path=str(args.output / "bloqueo.png"), full_page=True)
            checks.append(
                "Bloqueo circular por clic, exclusión y referencia sin cambios"
            )
            page.get_by_role(
                "button", name="Resolver bloqueos simulados", exact=True
            ).click()
            restored = calculate()
            assert restored["status"] == "ready"
            checks.append("Resolución explícita de eventos")
            page.get_by_label("Destino · longitud, latitud", exact=True).fill(
                "-71.5, -33.05"
            )
            page.get_by_label("Destino · longitud, latitud", exact=True).press("Tab")
            outside = calculate()
            assert "error" in outside
            expect(page.locator(".alternative")).to_have_count(0)
            checks.append("Punto exterior rechazado sin dejar rutas antiguas")
            page.get_by_role("button", name="Restablecer", exact=True).click()
            expect(
                page.get_by_role("button", name="Calcular rutas aéreas", exact=True)
            ).to_be_disabled()
            page.get_by_role("button", name="Seleccionar inicio", exact=True).click()
            c = [-71.65, -33.09]
            pixel = page.evaluate(
                "c => {const p=map.latLngToContainerPoint([c[1],c[0]]);return {x:p.x,y:p.y}}",
                c,
            )
            page.locator("#map").click(position=pixel)
            first = page.locator("#origin").input_value()
            assert first != ", ".join(map(str, initial["origin"]))
            page.get_by_label("Destino · longitud, latitud", exact=True).fill(
                "-71.64, -33.085"
            )
            page.locator("#destination").press("Tab")
            second = page.locator("#destination").input_value()
            page.get_by_role("button", name="Intercambiar", exact=True).click()
            expect(page.locator("#origin")).to_have_value(second)
            expect(page.locator("#destination")).to_have_value(first)
            checks.append(
                "Origen libre por clic, coordenadas e intercambio de extremos"
            )
            page.get_by_role("button", name="Restablecer", exact=True).click()
            page.get_by_label(
                "Horas disponibles del pronóstico", exact=True
            ).select_option(hours[0])
            page.get_by_label(
                "Objetivos de vigilancia de ejemplo", exact=True
            ).select_option("1")
            calculate()
            page.get_by_text("Preferencias de la misión", exact=True).click()
            page.locator("#budget").fill("1")
            page.locator("#budget").press("Tab")
            limited = calculate()
            assert limited["status"] == "not_feasible"
            assert limited["remaining_s"] == 1
            page.locator("#budget").fill("1200")
            page.locator("#budget").press("Tab")
            page.locator("#wind-limit").fill("0.01")
            page.locator("#wind-limit").press("Tab")
            strict = calculate()
            assert strict["reason"] == "weather_outside_profile"
            page.locator("#wind-limit").fill("8")
            page.locator("#wind-limit").press("Tab")
            checks.append("Preferencias efectivas de presupuesto y meteorología")
            with page.expect_response(
                lambda r: r.url.endswith("/api/aereo/comparar")
                and r.request.method == "POST"
            ) as response:
                page.get_by_role(
                    "button", name="Comparar misiones y resiliencia", exact=True
                ).click()
            comparison = response.value.json()
            assert comparison["metrics"]["total_scenarios"] == 100
            expect(page.locator("#comparison-summary")).to_be_visible()
            expect(page.locator(".alternative")).to_have_count(4)
            page.locator("#comparison-summary").scroll_into_view_if_needed()
            page.screenshot(path=str(args.output / "comparacion.png"), full_page=True)
            checks.append("Cuatro misiones comparables y métrica de 100 escenarios")
            for route_id in ["D1", "D2", "P1", "P2"]:
                toggle = page.locator(f'[data-route-id="{route_id}"]')
                expect(toggle).to_be_checked()
                before = page.evaluate("routeLayer.getLayers().length")
                toggle.uncheck()
                assert page.evaluate("routeLayer.getLayers().length") == before - 1
                toggle.check()
                assert page.evaluate("routeLayer.getLayers().length") == before
            checks.append(
                "D1 D2 P1 P2 se ocultan y muestran individualmente sin desplazar geometrías"
            )
            page.locator("#history-limit").select_option("1")
            expect(page.locator(".alternative")).to_have_count(0)
            policy = calculate()
            assert policy["effective_profile"]["max_historical_class"] == 1
            with page.expect_download() as download:
                page.get_by_role(
                    "button", name="Descargar resultado y escenario", exact=True
                ).click()
            download.value.save_as(str(args.output / "exportacion_politica.json"))
            exported = json.loads(
                (args.output / "exportacion_politica.json").read_text(encoding="utf-8")
            )
            assert exported["request"]["preferences"]["max_historical_class"] == 1
            page.locator("#history-limit").select_option("")
            disabled_policy = calculate()
            assert disabled_policy["effective_profile"]["max_historical_class"] is None
            checks.append(
                "Política histórica opcional, invalidación y exportación del perfil efectivo"
            )
            page.locator("#method").select_option("reference")
            for index in ["1", "2", "3", "4"]:
                page.locator("#bases").select_option(index)
                routed = calculate()
                assert routed["status"] == "ready"
                assert routed["alternatives"][0]["return_path"]
            checks.append("Las cuatro bases externas aprobadas funcionan por selección")
            origin = [
                float(v.strip())
                for v in page.locator("#origin").input_value().split(",")
            ]
            page.locator("#origin").fill(f"{origin[0]+0.00003}, {origin[1]}")
            page.locator("#origin").press("Tab")
            rejected = calculate()
            assert "Origen externo" in rejected["error"]
            checks.append("Origen externo libre rechazado y mapa anterior invalidado")
            page.get_by_role("button", name="Restablecer", exact=True).click()
            page.locator("#method").select_option("proposed")
            page.locator("#weather-hour").select_option(hours[0])
            page.locator("#examples").select_option("1")
            mission = calculate()
            page.get_by_text("Estado de misión y replanificación", exact=True).click()
            page.locator("#position").select_option(index=2)
            page.locator("#phase").select_option("emergency_return")
            page.locator("#elapsed").fill("100")
            with page.expect_response(
                lambda r: r.url.endswith("/api/aereo/replanificar")
            ) as response:
                page.get_by_role(
                    "button", name="Replanificar misión", exact=True
                ).click()
            replanned = response.value.json()
            assert replanned["status"] == "ready"
            assert not replanned["alternatives"][0]["mission_completed"]
            assert replanned["remaining_s"] == 1100
            checks.append(
                "Retorno de emergencia sin reiniciar autonomía ni completar vigilancia"
            )
            page.get_by_role("button", name="Restablecer", exact=True).click()
            page.locator("#weather-hour").select_option(hours[0])
            page.locator("#examples").select_option("1")
            calculate()
            page.locator("#alternatives").scroll_into_view_if_needed()
            page.screenshot(path=str(args.output / "resultado.png"), full_page=True)
            mobile = browser.new_page(
                viewport={"width": 390, "height": 844}, device_scale_factor=1
            )
            mobile.goto(args.url)
            mobile.wait_for_load_state("networkidle")
            expect(
                mobile.get_by_role(
                    "heading", name="Rutas aéreas para drones", exact=True
                )
            ).to_be_visible()
            assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth")
            mobile.screenshot(path=str(args.output / "movil.png"), full_page=True)
            mobile.close()
            checks.append("Vista móvil sin desbordamiento horizontal")
            assert not errors, errors
            report = dict(
                recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                successful=True,
                checks=checks,
                page_errors=errors,
                browser=browser.version,
                channel=args.channel,
                url=args.url,
                initial=initial,
                blocked=blocked,
                comparison=comparison,
                replanned=replanned,
                history_policy=policy,
            )
            (args.output / "resultado.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    dict(successful=True, checks=checks, page_errors=errors),
                    ensure_ascii=False,
                )
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()

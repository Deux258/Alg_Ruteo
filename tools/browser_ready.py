"""Wait for the application and its own data, independently of external tiles."""


def wait_patrol_ready(page, timeout=300000):
    # OpenStreetMap can leave an individual image request pending while every
    # local layer is ready. Network idleness does not describe application state.
    page.wait_for_function("""() => {
        const base=document.querySelector('#base');
        const status=document.querySelector('#geography-status');
        const geographicExport=document.querySelector('#export-geography');
        return base?.options.length>0 && !!document.querySelector('#geo-buildings') &&
            status?.getAttribute('aria-busy')==='false' &&
            geographicExport && !geographicExport.disabled;
    }""", timeout=timeout)

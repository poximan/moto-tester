# Fuentes por vista

`trasvase-tester/app/main.py` y `frontend/src/App.tsx` solo componen capacidades.

| Vista | Presentacion | API | Servicio | Estado o adaptador |
| --- | --- | --- | --- | --- |
| Overview y polling | `StatusHeader.tsx`, `MetricGrid.tsx`, `PollingControl.tsx` | `capabilities/overview/overview_api.py` | `overview_service.py` | `RuntimeState` y `SnapshotHub` |
| Proceso | `ProcessPanel.tsx` | `capabilities/process/process_api.py` | `process_service.py` | `adapters/emulator_client.py` |
| Bombas | `PumpGrid.tsx`, `PumpCard.tsx` | `capabilities/pumps/pumps_api.py` | `pumps_service.py` | `RuntimeState` y `EmulatorClient` |
| Tablas de produccion | `ProductionTables.tsx` | `capabilities/production/production_api.py` | `production_service.py` | `RuntimeState` y mapa de configuracion |
| Inyeccion | `InjectionPanel.tsx` | `capabilities/injection/injection_api.py` | `injection_service.py` | `RuntimeState` e `InjectionModeStore` |
| Diagnostico y logs | `LogsPanel.tsx` | `capabilities/diagnostics/diagnostics_api.py` | `diagnostics_service.py` | `logging_utils.py` |

`RuntimeState`, `SnapshotHub` y `EmulatorClient` son compartidos porque representan
una unica sesion Modbus, un unico stream y un unico servicio experto. Separarlos por
vista duplicaria la fuente operativa y la correlacion de escrituras.

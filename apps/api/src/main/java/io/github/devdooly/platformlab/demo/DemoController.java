package io.github.devdooly.platformlab.demo;

import java.time.Clock;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController @RequestMapping("/api/demo/runs")
public class DemoController {
    private final DemoService demos;
    private final Clock clock;
    public DemoController(DemoService demos, Clock clock) { this.demos = demos; this.clock = clock; }
    @GetMapping public Map<String, Object> list() { return demos.list(); }
    @GetMapping("/{id}") public Map<String, Object> detail(@PathVariable String id) { return demos.detail(id); }
    @ExceptionHandler(DemoService.RunNotFoundException.class) @ResponseStatus(HttpStatus.NOT_FOUND)
    public Map<String, Object> notFound() { return Map.of("code", "RUN_NOT_FOUND", "message", "요청한 실행 결과가 없습니다.", "observedAt", clock.instant()); }
}

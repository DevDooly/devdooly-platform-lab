package io.github.devdooly.platformlab.demo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.context.annotation.Profile;

@Component
@Profile("!worker & !admin")
public class SampleBootstrap implements ApplicationRunner {
    private final DemoService demos;
    public SampleBootstrap(DemoService demos) { this.demos = demos; }
    @Override public void run(ApplicationArguments args) { demos.ensureSample(); }
}

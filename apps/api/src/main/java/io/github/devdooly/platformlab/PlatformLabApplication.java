package io.github.devdooly.platformlab;

import java.time.Clock;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PlatformLabApplication {
    public static void main(String[] args) { SpringApplication.run(PlatformLabApplication.class, args); }
    @Bean Clock clock() { return Clock.systemUTC(); }
}

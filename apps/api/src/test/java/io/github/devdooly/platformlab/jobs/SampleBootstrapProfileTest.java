package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.DemoService;
import io.github.devdooly.platformlab.demo.SampleBootstrap;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.mock;

class SampleBootstrapProfileTest {
    @Test void defaultRetainsBootstrapButWorkerAndAdminDoNotRegisterIt() {
        assertThat(registered()).isTrue();
        assertThat(registered("test")).isTrue();
        assertThat(registered("worker")).isFalse();
        assertThat(registered("admin")).isFalse();
        assertThat(registered("test", "worker")).isFalse();
    }
    private boolean registered(String... profiles) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.getEnvironment().setActiveProfiles(profiles);
            context.registerBean(DemoService.class, () -> mock(DemoService.class));
            context.register(SampleBootstrap.class);
            context.refresh();
            return !context.getBeansOfType(SampleBootstrap.class).isEmpty();
        }
    }
}

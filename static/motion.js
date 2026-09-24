// ponytail: check reduced motion once at load; listen if an OS toggle must stop motion already running
if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
  anime({
    targets: ".signin, .heading, .notice, .error, .booking, .empty",
    opacity: [0, 1],
    translateY: [16, 0],
    delay: anime.stagger(50),
    duration: 480,
    easing: "easeOutCubic",
  });
  anime({
    targets: "aside",
    opacity: [0, 1],
    translateX: [24, 0],
    duration: 520,
    easing: "easeOutCubic",
  });
}

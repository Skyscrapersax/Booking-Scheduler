// ponytail: check reduced motion once at load; listen for changes if a live OS toggle must stop a running loop
if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
  anime({
    targets: ".App-logo",
    rotate: "1turn",
    easing: "linear",
    duration: 20000,
    loop: true,
  });
  anime({
    targets: ".heart",
    scale: [1, 1.25],
    direction: "alternate",
    easing: "easeInOutSine",
    duration: 700,
    loop: true,
  });
}

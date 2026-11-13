/**
 * 图片懒加载占位插件 JavaScript
 *
 * 与 image_lazy_loading 插件配合：服务端把真实图片地址写入 data-src，
 * src 先放内联 SVG 骨架占位。本脚本在图片进入视口（预留 200px 提前量）时
 * 把 data-src 回填到 src；浏览器不支持 IntersectionObserver 时直接全部加载。
 * 加载失败的兜底由 img 标签内联 onerror 处理，本脚本不重复实现。
 */
(function () {
    'use strict';

    function loadImage(img) {
        var realSrc = img.getAttribute('data-src');
        if (realSrc) {
            img.src = realSrc;
            img.removeAttribute('data-src');
        }
    }

    function initLazyLoad() {
        var images = document.querySelectorAll('img.lazy-img[data-src]');
        if (!images.length) {
            return;
        }

        // 降级：无 IntersectionObserver 支持时直接加载所有占位图
        if (!('IntersectionObserver' in window)) {
            Array.prototype.forEach.call(images, loadImage);
            return;
        }

        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    loadImage(entry.target);
                    observer.unobserve(entry.target);
                }
            });
        }, { rootMargin: '200px 0px' });

        Array.prototype.forEach.call(images, function (img) {
            observer.observe(img);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLazyLoad);
    } else {
        initLazyLoad();
    }
})();

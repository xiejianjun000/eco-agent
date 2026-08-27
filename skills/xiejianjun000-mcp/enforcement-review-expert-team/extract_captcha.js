async (page) => {
  const base64 = await page.evaluate(() => {
    const imgs = document.querySelectorAll('img');
    for (let img of imgs) {
      if (img.src && img.src.indexOf('code') >= 0) {
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth || img.width;
        canvas.height = img.naturalHeight || img.height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);
        return canvas.toDataURL('image/png');
      }
    }
    return null;
  });
  return base64;
}

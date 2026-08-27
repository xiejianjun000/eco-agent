async (page) => {
  const base64 = await page.evaluate(() => {
    const imgs = document.querySelectorAll('img');
    for (const img of imgs) {
      if (img.src && img.src.includes('code')) {
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);
        return canvas.toDataURL('image/png');
      }
    }
    return null;
  });
  
  if (base64) {
    return base64.replace('data:image/png;base64,', '');
  }
  return 'FAILED';
}

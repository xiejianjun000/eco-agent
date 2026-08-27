async (page) => {
  // Add ID to captcha image and get base64
  const captchaBase64 = await page.evaluate(() => {
    const imgs = document.querySelectorAll('img');
    for (const img of imgs) {
      if (img.src && img.src.includes('code')) {
        img.id = 'captchaImg';
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        canvas.getContext('2d').drawImage(img, 0, 0);
        return canvas.toDataURL('image/png');
      }
    }
    return null;
  });
  
  return { captchaBase64: captchaBase64 };
}

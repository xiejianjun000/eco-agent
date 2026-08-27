async (page) => {
  // Reload page for clean state
  await page.reload();
  await page.waitForTimeout(2000);
  
  // Fill credentials
  const usernameInput = page.getByRole('textbox', { name: '登录账户' });
  const passwordInput = page.getByRole('textbox', { name: '密码' });
  await usernameInput.fill(process.env.ECOAEGIS_ATMOSPHERE_USER || '430000');
  const pass = process.env.ECO_PASS || require('child_process').execSync('security find-generic-password -a ecoaegis -s atmosphere-pass -w', { encoding: 'utf8' }).trim();
  await passwordInput.fill(pass);
  
  // Extract captcha as base64
  const captchaBase64 = await page.evaluate(() => {
    const imgs = document.querySelectorAll('img');
    for (const img of imgs) {
      if (img.src && img.src.includes('code')) {
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        canvas.getContext('2d').drawImage(img, 0, 0);
        return canvas.toDataURL('image/png');
      }
    }
    return null;
  });
  
  if (!captchaBase64) {
    return { error: 'Captcha not found' };
  }
  
  // Save to file for external OCR
  const fs = require('fs');
  const path = require('path');
  const b64data = captchaBase64.replace('data:image/png;base64,', '');
  const b64path = path.join(process.cwd(), 'captcha_b64.txt');
  fs.writeFileSync(b64path, b64data);
  
  return { 
    ready: true, 
    msg: 'Captcha extracted, ready for OCR and submission',
    b64Len: b64data.length
  };
}

// source --> https://www.softconcis.de/assets/vendor/i18n/res/js/cookies/language-cookie.js?ver=494000 
document.addEventListener('DOMContentLoaded', function() {
	for(var cookieName in scl_cookies) {
		var cookieData = scl_cookies[cookieName];
		document.cookie = cookieName + '=' + cookieData.value + ';expires=' + cookieData.expires + '; path=' + cookieData.path + '; SameSite=Lax';
	}
});
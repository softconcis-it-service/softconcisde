document.addEventListener('DOMContentLoaded', function() {
	for(var cookieName in scl_cookies) {
		var cookieData = scl_cookies[cookieName];
		document.cookie = cookieName + '=' + cookieData.value + ';expires=' + cookieData.expires + '; path=' + cookieData.path + '; SameSite=Lax';
	}
});
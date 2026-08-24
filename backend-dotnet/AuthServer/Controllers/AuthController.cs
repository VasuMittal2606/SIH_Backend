using Microsoft.AspNetCore.Mvc;
using Microsoft.IdentityModel.Tokens;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;

namespace AuthServer.Controllers;

[ApiController]
[Route("api/[controller]")]
public class AuthController : ControllerBase
{
    private readonly IConfiguration _config;

    public AuthController(IConfiguration config)
    {
        _config = config;
    }

    [HttpPost("login")]
    public IActionResult Login([FromBody] LoginRequest request)
    {
        var (isValid, userId, role, district) = ValidateUserCredentials(request.Email, request.Password);

        if (!isValid)
        {
            return Unauthorized(new { message = "Invalid email or password" });
        }

        var secretKey = _config["JwtSettings:SecretKey"];
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secretKey!));
        var credentials = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        // Attach user role and district claims
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, userId),
            new Claim(ClaimTypes.Role, role),
            new Claim("district", district)
        };

        var token = new JwtSecurityToken(
            claims: claims,
            expires: DateTime.UtcNow.AddHours(8),
            signingCredentials: credentials
        );

        var tokenString = new JwtSecurityTokenHandler().WriteToken(token);

        return Ok(new
        {
            token = tokenString,
            user = new { userId, role, district }
        });
    }

    private (bool isValid, string userId, string role, string district) ValidateUserCredentials(string email, string password)
    {
        // Mock authentication aligning with ResidueLink dashboards
        return (email, password) switch
        {
            ("farmer@residuelink.com", "pass123") => (true, "USR_FARM_01", "Farmer", "Punjab_Zone_1"),
            ("chc@residuelink.com", "pass123") => (true, "USR_CHC_02", "CHC_Official", "Punjab_Zone_1"),
            ("buyer@residuelink.com", "pass123") => (true, "USR_BUY_03", "BiomassBuyer", "North_Region"),
            ("admin@residuelink.com", "pass123") => (true, "USR_ADM_00", "Admin", "All_Zones"),
            _ => (false, "", "", "")
        };
    }
}

public class LoginRequest
{
    public string Email { get; set; } = string.Empty;
    public string Password { get; set; } = string.Empty;
}